"""
Audit service (orchestrator).

Runs the full product audit from ONE page load:
1. Open the product page and verify the saved Amazon UK postcode.
2. Read the Buy Box / Featured Offer from that page.
3. Read the listing text (title, bullets, description, specifications).
4. A+ content, Brand Story and listing images: displayed or not.
5. Optional: do the A+ images show the same design as the listing?
6. Rules-based spelling check on the extracted text.
7. Listing quality rules (title, bullets, description, images).
8. Optional specification check against your uploaded template.
9. Optional: read the text inside the images (OCR). This runs in a
   background thread; batches collect it at the end (finish_image_text).

SPEED (version 0.21): the work is split in two.
- read_product_page(): ONLY what needs Chrome (open the page, read the
  Buy Box, text, image links, video links). A second or two per product.
- analyse_product(): everything else (downloads, design and colour
  checks, text inside images, spelling, quality, specification). It
  runs in the background (services/audit_engine.py) while Chrome is
  already reading the next product.

Each step's time is recorded in result["timings"] (seconds), and the
total in result["seconds"], so slow steps can be found.

The website (app.py) calls run_product_audit() and only displays
the result. Business logic stays here, not in the interface.
"""

import time
from concurrent.futures import Future
from datetime import datetime

from config.settings_manager import load_settings
from modules.buybox_audit import read_buy_box_from_page
from modules.listing_content import read_listing_content_from_page
from modules.amazon_extractor import extract_product_images
from modules.content_display import read_content_display, STATUS_NOT_DISPLAYED
from modules.design_match import (
    check_aplus_design,
    download_images,
    images_to_download,
    VERDICT_DIFFERENT,
    VERDICT_UNCERTAIN,
)
from modules.data_cleaner import clean_product_data
from modules.listing_audit import audit_listing
from modules.spec_checker import check_against_spec, amazon_variant_tokens
from modules.quality_rules import check_listing_quality
from modules import image_text
from modules.size_text import check_size_text, page_dimensions
from modules.visual_check import check_visual, read_video_thumbnails


class _Timer:
    """Records how long each audit step takes."""

    def __init__(self, result):
        self.result = result
        self.start = time.perf_counter()
        self.last = self.start

    def lap(self, step):
        now = time.perf_counter()
        self.result["timings"][step] = round(now - self.last, 2)
        self.last = now

    def total(self):
        self.result["seconds"] = round(time.perf_counter() - self.start, 1)


def _finish(result, status=None, timer=None):
    """Set the final status (if given), the total time and completion time."""

    if status:
        result["overall_status"] = status

    if timer:
        timer.total()

    result["completed_at"] = datetime.now().astimezone().isoformat()

    return result


def finish_image_text(result):
    """
    Wait for this product's background image reading (if any) and add
    its findings. Safe to call more than once.
    """

    content = result.get("content") or {}

    tokens = amazon_variant_tokens(
        content.get("technical_details") or {},
        {"selections": content.get("variations") or {}, "title": content.get("title", "")}
    )

    return image_text.finish(result, tokens, page_dims=page_dimensions(content))


def content_findings(display, design):
    """
    List the content problems worth a person's attention (pure function).
    Each finding: {"Item", "Status", "Detail"}.
    """

    findings = []

    # A+ and Brand Story are judged per parent (services/family_checks.py):
    # missing A+ is only a problem when another listing of the family has it.
    labels = {
        "listing_images": "Listing images",
    }

    for key, label in labels.items():
        if (display.get(key) or {}).get("status") == STATUS_NOT_DISPLAYED:
            findings.append({
                "Item": label,
                "Status": STATUS_NOT_DISPLAYED,
                "Detail": f"{label} was not found on the live product page. "
                          "Check it in Seller Central."
            })

    overall = (design or {}).get("overall")

    if overall in (VERDICT_DIFFERENT, VERDICT_UNCERTAIN):
        findings.append({
            "Item": "A+ design match",
            "Status": overall,
            "Detail": "One or more A+ images may show a different design "
                      "from the listing images. Compare them by eye."
        })

    return findings


def new_result(product_url, audit_type):
    return {
        "product_url": product_url,
        "audit_type": audit_type,
        "started_at": datetime.now().astimezone().isoformat(),
        "buy_box": {},
        "content": {},
        "spelling": {},
        "spec_check": {},
        "content_display": {},
        "design_check": {},
        "content_findings": [],
        "quality": [],
        "image_text": {},
        "visual": {},
        "timings": {},
        "seconds": None,
        "overall_status": "NOT COMPLETED",
        "errors": []
    }


PARENT_JS = r"""
() => {
    const html = document.documentElement.innerHTML;
    const m = html.match(/"parentAsin"\s*:\s*"([A-Z0-9]{10})"/)
           || html.match(/data-parent-asin="([A-Z0-9]{10})"/);
    return m ? m[1] : "";
}
"""


def read_product_page(browser, product_url, audit_type="Full Listing Audit", check_design=False):
    """
    Everything that needs Chrome, for one product. Returns a result that
    analyse_product() completes. Must run on the browser's own thread.
    result["_done"] is True when nothing is left to analyse (failed,
    blocked or location not verified).
    """

    result = new_result(product_url, audit_type)
    timer = _Timer(result)
    result["_timer_start"] = timer.start
    result["_done"] = True

    try:
        page, location = browser.open_product(product_url)
    except Exception as error:
        result["errors"].append("The product page could not be opened: " + str(error))
        return _finish(result, "FAILED", timer)

    timer.lap("Open page")

    try:
        expected_seller = load_settings().get("expected_seller", "")
        buy_box = read_buy_box_from_page(page, location, expected_seller)
        buy_box["product_url"] = product_url
        result["buy_box"] = buy_box
    except Exception as error:
        result["errors"].append("Buy Box check failed: " + str(error))
        return _finish(result, "FAILED", timer)

    timer.lap("Buy Box")

    if location.get("security_challenge"):
        result["errors"].append(
            "Amazon showed a security check. It was not bypassed, so nothing was read."
        )
        return _finish(result, "BLOCKED BY AMAZON", timer)

    if not location.get("verified"):
        result["errors"].append(
            location.get("help")
            or "Amazon location is not verified. Listing results were not checked."
        )
        return _finish(result, "LOCATION NOT VERIFIED", timer)

    try:
        content = read_listing_content_from_page(page, location, product_url)
        result["content"] = content
    except Exception as error:
        result["errors"].append("Listing extraction failed: " + str(error))
        return _finish(result, "PARTIAL - EXTRACTION FAILED", timer)

    timer.lap("Listing text")

    if content.get("status") != "EXTRACTED":
        result["errors"].append("Listing content status: " + str(content.get("status")))

    try:
        result["content_display"] = read_content_display(
            page, location, extract_product_images(page)
        )
    except Exception as error:
        result["errors"].append("Content display check failed: " + str(error))

    try:
        result["parent_asin"] = page.evaluate(PARENT_JS) or ""
    except Exception:
        result["parent_asin"] = ""

    if check_design:
        result["_video_urls"] = read_video_thumbnails(page)

    timer.lap("A+ / images")

    result["page_seconds"] = round(time.perf_counter() - timer.start, 1)
    result["_done"] = False

    return result


def analyse_product(result, spec=None, check_design=False, check_text=False):
    """
    The checks that do not need Chrome (safe on any thread). Completes
    the result from read_product_page() and returns it.
    """

    if result.pop("_done", True):
        result.pop("_timer_start", None)
        result.pop("_video_urls", None)
        return result

    timer = _Timer(result)
    timer.start = result.pop("_timer_start", timer.start)

    content = result.get("content") or {}
    display = result["content_display"] or {}

    # Download the images ONCE (cached across listings of a family).
    images = {}

    if (check_design or check_text) and display:

        wanted = images_to_download(display) if check_design else [
            url for _, _, url in image_text.choose_images(display)
            if image_text.cached_text(url) is None
        ]

        try:
            images = download_images(None, wanted)
        except Exception as error:
            result["errors"].append("Image download failed: " + str(error))

        timer.lap("Download images")

    if check_design and display:

        try:
            result["design_check"] = check_aplus_design(None, display, images)
        except Exception as error:
            result["errors"].append("A+ design check failed: " + str(error))

        try:
            result["visual"] = check_visual(None, content, display, images,
                                            video_urls=result.get("_video_urls") or [])
        except Exception as error:
            result["errors"].append("Colour / video check failed: " + str(error))

        timer.lap("Design + colour")

    result.pop("_video_urls", None)

    result["content_findings"] = content_findings(display, result["design_check"])

    cleaned = {}

    try:
        cleaned = clean_product_data(content)
        result["spelling"] = audit_listing(cleaned)
    except Exception as error:
        result["errors"].append("Spelling check failed: " + str(error))

    image_count = (display.get("listing_images") or {}).get("count") if display else None

    aplus_displayed = (display.get("aplus") or {}).get("status") not in (None, STATUS_NOT_DISPLAYED)

    result["quality"] = check_listing_quality(content, image_count, aplus_displayed)
    result["quality"] += check_size_text(content)

    if spec:
        try:
            result["spec_check"] = check_against_spec(
                cleaned.get("technical_details") or {},
                spec,
                variant_info={
                    "selections": content.get("variations") or {},
                    "title": content.get("title", ""),
                    "bullets": content.get("bullets") or [],
                    "description": content.get("description", ""),
                }
            )
        except Exception as error:
            result["errors"].append("Specification check failed: " + str(error))

    timer.lap("Spelling, quality, spec")

    set_status(result)

    # Text inside images (cached; one image at a time across all audits).
    if check_text and display:

        status, rows, seconds = image_text.read_all_now(image_text.choose_images(display), images)

        future = Future()
        future.set_result((status, rows, seconds))
        result["_image_text_future"] = future

        finish_image_text(result)

        timer.lap("Image text")

    _finish(result, None, timer)

    return result


def set_status(result):
    """Plain summary status for the interface."""

    summary = (result.get("spelling") or {}).get("summary", {})

    confirmed = (
        summary.get("confirmed_errors", 0)
        + len((result.get("spec_check") or {}).get("issues", []))
        + len(result.get("content_findings") or [])
        + sum(1 for finding in result.get("quality") or [] if finding["severity"] in ("High", "Medium"))
        + sum(1 for finding in (result.get("image_text") or {}).get("findings") or []
              if finding["severity"] in ("High", "Medium"))
    )

    if result.get("overall_status") in ("FAILED", "BLOCKED BY AMAZON", "LOCATION NOT VERIFIED"):
        return

    if result.get("errors"):
        result["overall_status"] = "COMPLETED WITH WARNINGS"
    elif confirmed:
        result["overall_status"] = "ISSUES FOUND"
    else:
        result["overall_status"] = "NO RULE-BASED ISSUES FOUND"


def run_product_audit(product_url, audit_type="Full Listing Audit", spec=None, browser=None,
                      check_design=False, check_text=False, defer_text=False):
    """
    Audit one product. With browser=None it goes through the shared
    audit engine (the same Chrome as every other audit). With a browser
    (tests, tools) both steps run here, one after the other.
    """

    if browser is None:
        from services.audit_engine import get_engine
        batch = get_engine().submit(
            [{"url": product_url, "asin": ""}], audit_type, spec, check_design, check_text
        )
        return batch.wait()[0]

    result = read_product_page(browser, product_url, audit_type, check_design)

    return analyse_product(result, spec, check_design, check_text)
