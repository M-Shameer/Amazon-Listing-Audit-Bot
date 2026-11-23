"""
Tests for background (invisible) Chrome mode, the postcode wait and
the batch stopping early when the location is not verified.
No browser or internet needed.
"""

import unittest
from unittest import mock

from modules import amazon_session
from services import batch_audit_service
from tests.test_quality import FakePage, FakeContext


class BrowserModeTests(unittest.TestCase):

    def setUp(self):
        self._load = amazon_session.load_settings

    def tearDown(self):
        amazon_session.load_settings = self._load

    def use_settings(self, **values):
        settings = {"delivery_postcode": "SW1A 1AA", "browser_profile": "data/test_profile"}
        settings.update(values)
        amazon_session.load_settings = lambda: settings

    def test_background_is_the_default(self):
        self.use_settings()
        self.assertTrue(amazon_session.AmazonBrowser().headless)

    def test_setting_off_shows_the_window(self):
        self.use_settings(background_browser=False)
        self.assertFalse(amazon_session.AmazonBrowser().headless)

    def test_verify_window_is_always_visible(self):
        self.use_settings(background_browser=True)
        self.assertFalse(amazon_session.AmazonBrowser(visible=True).headless)


class WrongPostcodePage(FakePage):
    """Amazon shows another postcode until `fixed_after` reads."""

    def __init__(self, fixed_after=None):
        super().__init__("main")
        self.reads = 0
        self.fixed_after = fixed_after

    def locator(self, selector):
        page = self

        class Locator:
            first = None

            def count(self):
                if "captcha" in selector.lower():
                    return 0
                return 1

            def inner_text(self, timeout=None):
                page.reads += 1
                if page.fixed_after is not None and page.reads > page.fixed_after:
                    return "Deliver to London SW1A 1AA"
                return "Deliver to Karachi 75500"

        locator = Locator()
        locator.first = locator
        return locator


class PostcodeWaitTests(unittest.TestCase):

    def test_wait_returns_when_person_sets_postcode(self):
        page = WrongPostcodePage(fixed_after=2)
        header = amazon_session.wait_for_saved_postcode(page, "SW1A 1AA", seconds=30)
        self.assertIn("SW1A 1AA", header)

    def test_wait_gives_up_after_time_limit(self):
        page = WrongPostcodePage(fixed_after=None)
        header = amazon_session.wait_for_saved_postcode(page, "SW1A 1AA", seconds=0)
        self.assertNotIn("SW1A 1AA", header)

    def test_background_mode_never_waits_or_prompts(self):
        self._mark = amazon_session.mark_location_verified
        amazon_session.mark_location_verified = lambda *args: None
        try:
            browser = object.__new__(amazon_session.AmazonBrowser)
            browser.postcode = "SW1A 1AA"
            browser.headless = True
            browser.context = FakeContext()
            browser.page = WrongPostcodePage(fixed_after=None)
            browser.prompted = False
            browser.prefetched = {}
            browser.next_url = None
            browser.extra_tab = None
            browser.upcoming = []
            browser.auto_set_tried = False

            page, report = browser.open_product("https://www.amazon.co.uk/dp/B000000001")

            self.assertFalse(report["verified"])
            self.assertIn("Verify Location in Chrome", report["help"])
            self.assertFalse(browser.prompted)
            # The automatic "Deliver to" setting was tried once.
            self.assertTrue(browser.auto_set_tried)
        finally:
            amazon_session.mark_location_verified = self._mark


class AmazonLikePage(FakePage):
    """
    Shows "Pakistan" until the postcode is typed into Amazon's own
    "Deliver to" box and applied.
    """

    def __init__(self):
        super().__init__("main")
        self.header = "Deliver to Pakistan"
        self.typed = ""
        self.clicked = []

    def locator(self, selector):
        page = self

        class Locator:
            def __init__(self):
                self.first = self

            def count(self):
                return 0 if "captcha" in selector.lower() else 1

            def is_visible(self):
                return True

            def inner_text(self, timeout=None):
                return page.header

            def click(self, timeout=None):
                page.clicked.append(selector)
                if "GLUXZipUpdate" in selector and page.typed:
                    page.header = "Deliver to London " + page.typed

            def wait_for(self, state=None, timeout=None):
                return None

            def fill(self, text):
                page.typed = text

        return Locator()


class AutoPostcodeTests(unittest.TestCase):

    def setUp(self):
        self._mark = amazon_session.mark_location_verified
        amazon_session.mark_location_verified = lambda *args: None

    def tearDown(self):
        amazon_session.mark_location_verified = self._mark

    def make_browser(self, page):
        browser = object.__new__(amazon_session.AmazonBrowser)
        browser.postcode = "SW1A 1AA"
        browser.headless = True
        browser.context = FakeContext()
        browser.page = page
        browser.prompted = False
        browser.prefetched = {}
        browser.next_url = None
        browser.extra_tab = None
        browser.upcoming = []
        browser.auto_set_tried = False
        return browser

    def test_postcode_is_set_in_amazons_own_box(self):
        page = AmazonLikePage()
        browser = self.make_browser(page)

        _, report = browser.open_product("https://www.amazon.co.uk/dp/B000000001")

        self.assertTrue(report["verified"])
        self.assertEqual(page.typed, "SW1A 1AA")
        # Only the delivery-location box was used.
        for selector in page.clicked:
            self.assertTrue("location" in selector.lower() or "glow" in selector.lower()
                            or "glux" in selector.lower() or "popover" in selector.lower(),
                            selector)

    def test_two_products_load_ahead(self):
        page = AmazonLikePage()
        page.header = "Deliver to London SW1A 1AA"
        browser = self.make_browser(page)
        browser.upcoming = ["https://www.amazon.co.uk/dp/B000000002",
                            "https://www.amazon.co.uk/dp/B000000003"]

        browser.open_product("https://www.amazon.co.uk/dp/B000000001")

        self.assertEqual(len(browser.prefetched), 2)


class FakeBrowser:
    def __init__(self):
        self.next_url = None
        self.upcoming = []

    def start(self):
        pass

    def close(self):
        pass


class BatchStopTests(unittest.TestCase):

    def setUp(self):
        from services import audit_engine
        self.engine_module = audit_engine
        self.calls = []

        def fake_read(browser, url, *args, **kwargs):
            self.calls.append(url)
            return {"overall_status": "LOCATION NOT VERIFIED", "errors": ["Use Verify Location."],
                    "_done": True}

        audit_engine.reset_engine()
        self.patches = [
            mock.patch.object(audit_engine, "AmazonBrowser", FakeBrowser),
            mock.patch.object(audit_engine, "read_product_page", fake_read),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        self.engine_module.reset_engine()
        for patch in self.patches:
            patch.stop()

    def test_batch_stops_after_location_failure(self):
        items = [{"url": f"https://www.amazon.co.uk/dp/B00000000{n}", "asin": f"B00000000{n}"}
                 for n in range(1, 5)]

        results = batch_audit_service.run_batch_audit(items)

        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(results), 4)
        self.assertTrue(all(r["overall_status"] == "LOCATION NOT VERIFIED" for r in results))
        self.assertIn("Use Verify Location.", results[3]["errors"][0])


if __name__ == "__main__":
    unittest.main()
