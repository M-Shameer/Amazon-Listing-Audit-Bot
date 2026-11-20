"""
Tests for the one-browser, one-page-load audit flow.

A fake browser stands in for Chrome, so no Amazon page is opened.
It records how many times Chrome was started and how many pages
were loaded, to prove each product is loaded only once.

Run from the project folder:
    python -m unittest discover -s tests -t . -v
"""

import unittest
from unittest import mock

import services.audit_service as audit_service
import services.batch_audit_service as batch_service

from tests.test_buybox import FakeElement, REAL_TEXT_DISPATCHES


class FakeLocator:
    """Supports what the Buy Box and listing readers call on a locator."""

    def __init__(self, texts):
        self.texts = texts

    def count(self):
        return len(self.texts)

    def nth(self, index):
        return FakeElement(self.texts[index])

    @property
    def first(self):
        return FakeLocator(self.texts[:1])

    def inner_text(self, timeout=None):
        return self.texts[0]

    def all_inner_texts(self):
        return list(self.texts)


class FakePage:
    """Stands in for a Playwright page: selector -> list of visible texts."""

    def __init__(self, elements):
        self.elements = elements

    def locator(self, selector):
        return FakeLocator(self.elements.get(selector, []))


PAGE_ELEMENTS = {
    "#desktop_buybox": [REAL_TEXT_DISPATCHES],
    "#add-to-cart-button": ["Add to basket"],
    "#buy-now-button": ["Buy Now"],
    "#corePrice_feature_div .a-offscreen": ["£17.99"],
    "#availability": ["In stock"],
    "#productTitle": ["Brightbed Double Duvet Set Premium Brushed Microfiber Duvet Cover"],
}


class FakeBrowser:
    """Counts starts and page loads instead of opening Chrome."""

    starts = 0
    loads = 0
    location_ok = True

    def start(self):
        FakeBrowser.starts += 1

    def restart(self):
        self.start()

    def close(self):
        pass

    def open_product(self, url):
        FakeBrowser.loads += 1
        location = {
            "verified": FakeBrowser.location_ok,
            "security_challenge": False,
            "amazon_header": "London SW1A1AA"
        }
        return FakePage(PAGE_ELEMENTS), location


class AuditFlowTests(unittest.TestCase):

    def setUp(self):
        FakeBrowser.starts = 0
        FakeBrowser.loads = 0
        FakeBrowser.location_ok = True

    def run_batch(self, count):
        items = [
            {"url": f"https://www.amazon.co.uk/dp/B0AAAAAA0{n}", "asin": f"B0AAAAAA0{n}"}
            for n in range(count)
        ]
        with mock.patch.object(batch_service, "AmazonBrowser", FakeBrowser), \
             mock.patch.object(audit_service, "load_settings",
                               return_value={"expected_seller": "Northwind LTD"}), \
             mock.patch("modules.listing_content.extract_technical_details", return_value={}):
            return batch_service.run_batch_audit(items, "Full Listing Audit")

    def test_chrome_opens_once_and_each_page_loads_once(self):
        results = self.run_batch(3)

        self.assertEqual(FakeBrowser.starts, 1)
        self.assertEqual(FakeBrowser.loads, 3)
        self.assertEqual(len(results), 3)

    def test_buy_box_and_text_read_from_same_page(self):
        result = self.run_batch(1)[0]

        self.assertEqual(result["buy_box"]["featured_offer_verdict"], "HELD BY YOUR SELLER")
        self.assertEqual(result["buy_box"]["dispatches_from"], "Amazon")
        self.assertTrue(result["content"]["title"].startswith("Brightbed"))
        self.assertEqual(result["overall_status"], "ISSUES FOUND")  # Microfiber in title

    def test_wrong_location_reads_nothing(self):
        FakeBrowser.location_ok = False

        result = self.run_batch(1)[0]

        self.assertEqual(result["overall_status"], "LOCATION NOT VERIFIED")
        self.assertEqual(result["content"], {})


if __name__ == "__main__":
    unittest.main()
