"""
Shared Amazon UK browser session.

Opens Amazon UK product pages using the persistent Chromium profile,
checks that Amazon is actually using the postcode saved in
config/settings.json, and only then lets the caller read the page.

SPEED (version 0.10):
- AmazonBrowser opens Chrome ONCE and reuses it for a whole batch.
- Each product page is loaded ONCE; the Buy Box and the listing text
  are both read from that same page.
- Instead of a fixed 3-second pause, the code waits only until the
  product title (or a security page) appears.

SPEED (version 0.12):
- While one product is being checked, the NEXT product already loads
  in a second tab ("prefetch"), so its page is ready when needed.
- The security-page check no longer reads the whole page text.

BACKGROUND MODE (version 0.13):
- By default Chrome runs invisibly (no window, nothing in the taskbar),
  using the same saved profile, so the postcode and session are kept.
- The terminal "press ENTER" prompt is gone. The location is set with
  verify_location_in_window(), started by the "Verify Location" button
  on the Delivery Location page: it opens ONE visible window and waits
  until Amazon shows the saved postcode.

AUTOMATIC POSTCODE (version 0.15):
- When Amazon is not using the saved postcode (for example it shows
  "Pakistan" because of the internet location), the bot types the
  postcode into Amazon's own "Deliver to" box, exactly as a person
  would, and checks the header again. Only the delivery-location box
  is used: never basket, buy or offer buttons.

SPEED (version 0.15):
- Up to PREFETCH_AHEAD products load in background tabs at once.
- Videos on product pages do not autoplay (less to download).

This module does not bypass CAPTCHA or any Amazon security check.
"""

import re
import time
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

from config.settings_manager import (
    load_settings,
    mark_location_verified,
    normalise_postcode
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# How long to wait for the product page to show its title (milliseconds).
PAGE_READY_TIMEOUT = 20000

# Short pause after the title appears, so the purchase box can finish.
SETTLE_MS = 800

# A page loaded in advance has had time to finish, so a shorter pause.
SETTLE_PREFETCHED_MS = 250

AMAZON_HOME = "https://www.amazon.co.uk/"

# How many next products load in background tabs at the same time.
PREFETCH_AHEAD = 2

# Amazon's own delivery-location box (the "Deliver to" link at the top).
LOCATION_LINK = "#nav-global-location-popover-link, #glow-ingress-block"
POSTCODE_INPUT = "#GLUXZipUpdateInput"
POSTCODE_APPLY = "#GLUXZipUpdate input, #GLUXZipUpdate"
POPOVER_CLOSE = (
    "#GLUXConfirmClose, button[name='glowDoneButton'], "
    ".a-popover-footer .a-button-primary input, .a-popover .a-button-close"
)

# Visible window: how long to wait for the person to set the postcode.
LOCATION_WAIT_SECONDS = 180

LOCATION_HELP = (
    "Amazon is not using your saved postcode. Open the Delivery Location "
    "page and click \"Verify Location in Chrome\", then run the audit again."
)


def clean_text(text):
    """Remove extra spaces and line breaks."""

    if not isinstance(text, str):
        return ""

    return re.sub(r"\s+", " ", text).strip()


def read_delivery_header(page):
    """Read Amazon's delivery location text from the top of the page."""

    for selector in ["#glow-ingress-line2", "#glow-ingress-block"]:

        try:

            element = page.locator(selector).first

            if element.count() > 0:

                text = clean_text(
                    element.inner_text(timeout=3000)
                )

                if text:
                    return text

        except Exception:
            continue

    return ""


def is_security_challenge(page):
    """
    Detect Amazon's CAPTCHA or security page.
    The code only detects it. It never tries to get past it.
    """

    try:

        if page.locator("#captchacharacters, form[action*='validateCaptcha']").count() > 0:
            return True

        # A normal product page: no need to read the whole page text.
        if page.locator("#productTitle").count() > 0:
            return False

        body_text = clean_text(
            page.locator("body").inner_text(timeout=5000)
        ).lower()

        return (
            "sorry, we just need to make sure" in body_text
            or "enter the characters you see below" in body_text
        )

    except Exception:
        return False


def postcode_in_header(postcode, header):
    """Check whether the saved postcode appears in Amazon's header."""

    return normalise_postcode(postcode) in normalise_postcode(header)


def create_location_report(postcode):
    """Create the default location report."""

    return {
        "saved_postcode": postcode,
        "amazon_header": "",
        "location_status": "NOT VERIFIED",
        "verified": False,
        "security_challenge": False,
        "http_status": None,
        "page_title": ""
    }


def set_postcode_on_page(page, postcode):
    """
    Type the postcode into Amazon's own "Deliver to" box and apply it,
    the same way a person does. Then reload and re-read the header.
    Returns the header text afterwards ("" if it could not be done).
    Only the delivery-location box is touched.
    """

    try:
        page.locator(LOCATION_LINK).first.click(timeout=6000)

        box = page.locator(POSTCODE_INPUT).first
        box.wait_for(state="visible", timeout=8000)
        box.fill(postcode)

        page.locator(POSTCODE_APPLY).first.click(timeout=5000)

        # Amazon sometimes shows a "Done" / "Continue" confirmation.
        page.wait_for_timeout(1500)

        try:
            close = page.locator(POPOVER_CLOSE).first
            if close.count() > 0 and close.is_visible():
                close.click(timeout=3000)
        except Exception:
            pass

        page.reload(wait_until="domcontentloaded", timeout=60000)

        wait_until_ready(page)

        return read_delivery_header(page)

    except Exception:
        return ""


def wait_until_ready(page, settle_ms=SETTLE_MS):
    """
    Wait until the product page is usable, instead of a fixed pause.
    Never raises: a slow page is reported later as missing data.
    """

    try:
        page.wait_for_selector(
            "#productTitle, #captchacharacters, #glow-ingress-line2",
            timeout=PAGE_READY_TIMEOUT
        )
    except Exception:
        pass

    try:
        page.wait_for_selector(
            "#desktop_buybox, #buybox, #outOfStock, #availability",
            timeout=5000
        )
    except Exception:
        pass

    page.wait_for_timeout(settle_ms)


class AmazonBrowser:
    """
    One Chrome window for many products.

        with AmazonBrowser() as browser:
            for url in urls:
                page, location = browser.open_product(url)
                ... read the page ...

    Check location["verified"] before trusting price, delivery or
    Buy Box information. Only one AmazonBrowser may be open at a time,
    because Chrome locks its profile folder.
    """

    def __init__(self, visible=None):
        """
        visible: True shows the Chrome window, False hides it.
                 None (default) uses the saved "background_browser" setting.
        """

        settings = load_settings()

        if visible is None:
            visible = not settings.get("background_browser", True)

        self.headless = not visible

        self.postcode = settings.get("delivery_postcode", "")

        if not self.postcode:
            raise RuntimeError(
                "No delivery postcode is saved. Save one on the "
                "Delivery Location page first."
            )

        self.profile_dir = PROJECT_ROOT / settings.get(
            "browser_profile",
            "data/amazon_uk_profile"
        )

        self.playwright = None
        self.context = None
        self.page = None

        # The terminal prompt to fix the location is shown at most once.
        self.prompted = False

        # Pages loading in advance: {url: (tab, response)}.
        self.prefetched = {}

        # The batch sets this to the next product's link before each
        # product, so it can start loading in a second tab.
        self.next_url = None

        # Extra tab of the product being read (closed at the next product).
        self.extra_tab = None

        # The batch sets the links that come after the current product.
        self.upcoming = []

        # The automatic postcode setting is tried once per browser start.
        self.auto_set_tried = False

    # ---------- start / stop ----------

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def start(self):
        """Launch Chrome with the saved profile."""

        self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.playwright = sync_playwright().start()

        options = dict(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            locale="en-GB",
            timezone_id="Europe/London",
            viewport={"width": 1365, "height": 900},
            # Product videos do not start by themselves (faster pages).
            args=["--autoplay-policy=user-gesture-required"]
        )

        if self.headless:

            # "chromium" channel = the same full Chromium as the visible
            # window, in its new headless mode (keeps the same profile).
            try:
                self.context = self.playwright.chromium.launch_persistent_context(
                    channel="chromium", **options
                )
            except Exception:
                self.context = self.playwright.chromium.launch_persistent_context(**options)

        else:

            self.context = self.playwright.chromium.launch_persistent_context(**options)

        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def close(self):
        """Close Chrome and Playwright. Safe to call more than once."""

        self.prefetched = {}
        self.extra_tab = None
        self.auto_set_tried = False

        try:
            if self.context:
                self.context.close()
        except Exception:
            pass

        try:
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass

        self.context = None
        self.playwright = None
        self.page = None

    def restart(self):
        """Close and relaunch Chrome (used after a crash)."""

        self.close()
        self.start()

    # ---------- load the next product in advance ----------

    def prefetch(self, product_url):
        """
        Start loading a product in a second tab and return at once.
        Chrome keeps loading it while the current product is checked.
        """

        if not product_url or not self.context or product_url in self.prefetched:
            return

        tab = None

        try:
            tab = self.context.new_page()

            # "commit" returns as soon as Amazon starts answering.
            response = tab.goto(product_url, wait_until="commit", timeout=60000)

            self.prefetched[product_url] = (tab, response)

        except Exception:
            # Prefetch is only a speed-up; on failure the page loads normally.
            try:
                if tab:
                    tab.close()
            except Exception:
                pass

    def _close_extra_tab(self):
        """Close the extra tab of the previous product."""

        if self.extra_tab:
            try:
                self.extra_tab.close()
            except Exception:
                pass

        self.extra_tab = None

    # ---------- open one product ----------

    def open_product(self, product_url):
        """
        Load one product page and check the delivery location.
        Returns (page, location_report).
        """

        report = create_location_report(self.postcode)

        self._close_extra_tab()

        if product_url in self.prefetched:

            # Already loading (or loaded) in a second tab.
            page, response = self.prefetched.pop(product_url)

            self.extra_tab = page

            wait_until_ready(page, SETTLE_PREFETCHED_MS)

        else:

            page = self.page

            response = page.goto(
                product_url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            wait_until_ready(page)

        if response:
            report["http_status"] = response.status

        try:
            report["page_title"] = page.title()
        except Exception:
            pass

        if is_security_challenge(page):

            report["security_challenge"] = True
            report["location_status"] = "BLOCKED_OR_CHALLENGE"

            return page, report

        header = read_delivery_header(page)

        if not postcode_in_header(self.postcode, header) and page is self.extra_tab:

            # The page started loading before the location was fixed:
            # one reload picks up the saved postcode.
            page.reload(wait_until="domcontentloaded", timeout=60000)

            wait_until_ready(page)

            header = read_delivery_header(page)

        if not postcode_in_header(self.postcode, header) and not self.auto_set_tried:

            # Amazon forgot the location (e.g. shows the internet country):
            # set it in Amazon's own "Deliver to" box, once per browser start.
            self.auto_set_tried = True

            header = set_postcode_on_page(page, self.postcode) or read_delivery_header(page)

            # Tabs that were already loading used the old location.
            for tab, _ in self.prefetched.values():
                try:
                    tab.close()
                except Exception:
                    pass

            self.prefetched = {}

        if not postcode_in_header(self.postcode, header) and not self.prompted and not self.headless:

            # Visible window only, at most once per batch: give the person
            # time to set the postcode in the window (no terminal prompt).
            self.prompted = True

            header = wait_for_saved_postcode(page, self.postcode, LOCATION_WAIT_SECONDS)

        report["amazon_header"] = header

        if postcode_in_header(self.postcode, header):

            mark_location_verified(self.postcode, header)

            report["verified"] = True
            report["location_status"] = "VERIFIED - AMAZON USING SAVED POSTCODE"

        else:

            report["location_status"] = "NOT VERIFIED - AMAZON NOT USING SAVED POSTCODE"
            report["help"] = LOCATION_HELP

        # This page is ready: start loading the next products now, so they
        # load while this one is being read.
        upcoming = list(self.upcoming) or ([self.next_url] if self.next_url else [])

        for url in upcoming[:PREFETCH_AHEAD]:
            if url and url != product_url:
                self.prefetch(url)

        return page, report


def wait_for_saved_postcode(page, postcode, seconds):
    """
    Wait (up to `seconds`) while the person sets the postcode in the
    visible window. Amazon reloads the page itself after "Apply".
    Returns the last delivery header read. Never clicks anything.
    """

    deadline = time.monotonic() + seconds

    header = read_delivery_header(page)

    while not postcode_in_header(postcode, header) and time.monotonic() < deadline:

        try:
            page.wait_for_timeout(2000)
        except Exception:
            break   # the person closed the window

        header = read_delivery_header(page)

    return header


def verify_location_in_window(wait_seconds=LOCATION_WAIT_SECONDS):
    """
    Open ONE visible Chrome window on Amazon UK and wait until Amazon
    shows the saved postcode. The person sets it themselves:
    click the delivery location at the top, enter the postcode, Apply.
    If Amazon shows a security check, the person completes it in the
    window; the code never bypasses it.

    Returns {"verified", "postcode", "amazon_header", "message"}.
    """

    with AmazonBrowser(visible=True) as browser:

        page = browser.page

        page.goto(AMAZON_HOME, wait_until="domcontentloaded", timeout=60000)

        try:
            page.wait_for_selector("#glow-ingress-line2, #captchacharacters", timeout=20000)
        except Exception:
            pass

        header = read_delivery_header(page)

        if not postcode_in_header(browser.postcode, header):
            # Try Amazon's own "Deliver to" box first; the person can
            # still set it by hand while the window waits.
            header = set_postcode_on_page(page, browser.postcode) or header

        if not postcode_in_header(browser.postcode, header):
            header = wait_for_saved_postcode(page, browser.postcode, wait_seconds)

        verified = postcode_in_header(browser.postcode, header)

        if verified:
            mark_location_verified(browser.postcode, header)

        return {
            "verified": verified,
            "postcode": browser.postcode,
            "amazon_header": header,
            "message": (
                "Amazon is using your saved postcode."
                if verified else
                "Amazon still shows: " + (header or "(nothing)") + ". Try again."
            ),
        }


@contextmanager
def open_verified_amazon_page(product_url):
    """
    Open ONE product page (kept for single-page tools such as the
    Variation Matrix). Yields (page, report).
    """

    with AmazonBrowser() as browser:

        page, report = browser.open_product(product_url)

        yield page, report


if __name__ == "__main__":

    import time

    print("\n==========================================")
    print(" AMAZON UK SESSION SPEED TEST")
    print("==========================================")

    raw = input("\nEnter one or more Amazon UK URLs, separated by spaces: ").split()

    urls = [url for url in raw if url.startswith("https://www.amazon.co.uk/")]

    if not urls:

        print("\nPlease enter at least one valid Amazon UK product URL.")

    else:

        with AmazonBrowser() as browser:

            for url in urls:

                start = time.perf_counter()

                page, report = browser.open_product(url)

                print(
                    f"{time.perf_counter() - start:5.1f}s | "
                    f"{report['location_status']} | {report['page_title'][:60]}"
                )
