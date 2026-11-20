"""
Tests for the Buy Box reading and decision logic.

These tests do NOT open a browser or Amazon. They feed real text that
Amazon showed in earlier runs into the pure functions and check the result.

Run from the project folder:
    python -m unittest discover -s tests -t . -v
"""

import unittest

from modules.buybox_audit import (
    parse_seller_and_dispatch,
    classify_featured_offer,
    detect_currency,
    normalise_seller,
    VERDICT_YOURS,
    VERDICT_LOST,
    VERDICT_HELD,
    VERDICT_NONE,
    VERDICT_NOT_VERIFIED,
    VERDICT_BLOCKED,
    read_buy_box_from_page,
)


class FakeElement:
    def __init__(self, text):
        self.text = text

    def is_visible(self):
        return True

    def inner_text(self, timeout=None):
        return self.text


class FakeLocator:
    def __init__(self, texts):
        self.texts = texts

    def count(self):
        return len(self.texts)

    def nth(self, index):
        return FakeElement(self.texts[index])


class FakePage:
    """Stands in for a Playwright page: selector -> list of visible texts."""

    def __init__(self, elements):
        self.elements = elements

    def locator(self, selector):
        return FakeLocator(self.elements.get(selector, []))


# Real purchase-box text from batch_audit_20261113_010513.json (B0AAAAAA01)
REAL_TEXT_DISPATCHES = (
    "£17.99 £17 . 99 FREE Returns FREE delivery Monday, 16 November on your "
    "first order to UK or Ireland. Order within 55 mins. Details Deliver to "
    "London SW1A1AA In stock Quantity:1 Add to basket Buy Now Dispatches from "
    "Amazon Sold by Northwind Returns Returnable until Jan 31, 2027"
)

# Real purchase-box text from batch_audit_20261113_020600.json (B0AAAAAA04).
# The old code could not read "Dispatches From" from this wording.
REAL_TEXT_MANAGED = (
    "£19.99 £19 . 99 FREE Returns FREE delivery Saturday, 14 November. "
    "Details Deliver to London SW1A1AA In stock Quantity:1 Add to basket "
    "Buy Now Delivery Managed by Amazon Sold by Northwind Returns Returnable "
    "until Jan 31, 2027 Payment Secure transaction"
)


def verified_report(**changes):
    """A report where location is verified and a normal Buy Box is shown."""

    report = {
        "location": {"verified": True, "security_challenge": False},
        "purchase_area_found": True,
        "add_to_basket_visible": True,
        "buy_now_visible": True,
        "see_all_buying_options_visible": False,
        "availability": "In stock",
        "seller": "Northwind",
        "currency": "GBP",
    }

    report.update(changes)

    return report


class ParseSellerAndDispatchTests(unittest.TestCase):

    def test_real_dispatches_from_text(self):
        result = parse_seller_and_dispatch(REAL_TEXT_DISPATCHES)
        self.assertEqual(result["seller"], "Northwind")
        self.assertEqual(result["dispatches_from"], "Amazon")
        self.assertEqual(result["dispatch_wording"], "Dispatches from")

    def test_real_delivery_managed_by_text(self):
        result = parse_seller_and_dispatch(REAL_TEXT_MANAGED)
        self.assertEqual(result["seller"], "Northwind")
        self.assertEqual(result["dispatches_from"], "Amazon")
        self.assertEqual(result["dispatch_wording"], "Delivery Managed by")

    def test_ships_from(self):
        result = parse_seller_and_dispatch("Ships from Amazon Sold by Home Store Ltd Returns")
        self.assertEqual(result["seller"], "Home Store Ltd")
        self.assertEqual(result["dispatches_from"], "Amazon")

    def test_dispatches_from_and_sold_by_amazon(self):
        result = parse_seller_and_dispatch("Dispatches from and sold by Amazon.co.uk Returns")
        self.assertEqual(result["seller"], "Amazon.co.uk")
        self.assertEqual(result["dispatches_from"], "Amazon.co.uk")

    def test_sold_by_and_fulfilled_by(self):
        result = parse_seller_and_dispatch("Sold by Northwind and Fulfilled by Amazon.")
        self.assertEqual(result["seller"], "Northwind")
        self.assertEqual(result["dispatches_from"], "Amazon")

    def test_empty_text_gives_empty_values(self):
        result = parse_seller_and_dispatch("")
        self.assertEqual(result["seller"], "")
        self.assertEqual(result["dispatches_from"], "")


class ClassifyFeaturedOfferTests(unittest.TestCase):

    def test_your_seller_holds_featured_offer(self):
        result = classify_featured_offer(verified_report(), "northwind")
        self.assertEqual(result["featured_offer_verdict"], VERDICT_YOURS)
        self.assertEqual(result["featured_offer_holder"], "Northwind")

    def test_another_seller_holds_featured_offer(self):
        result = classify_featured_offer(verified_report(seller="Other Shop"), "Northwind")
        self.assertEqual(result["featured_offer_verdict"], VERDICT_LOST)
        self.assertIn("Other Shop", result["featured_offer_status"])

    def test_no_expected_seller_still_names_holder(self):
        result = classify_featured_offer(verified_report(), "")
        self.assertEqual(result["featured_offer_verdict"], VERDICT_HELD)
        self.assertEqual(result["featured_offer_holder"], "Northwind")

    def test_location_not_verified_is_never_verified(self):
        report = verified_report(location={"verified": False})
        result = classify_featured_offer(report, "Northwind")
        self.assertEqual(result["featured_offer_verdict"], VERDICT_NOT_VERIFIED)

    def test_security_challenge_is_blocked(self):
        report = verified_report(location={"verified": False, "security_challenge": True})
        result = classify_featured_offer(report, "Northwind")
        self.assertEqual(result["featured_offer_verdict"], VERDICT_BLOCKED)

    def test_suppressed_buy_box(self):
        report = verified_report(
            add_to_basket_visible=False,
            buy_now_visible=False,
            see_all_buying_options_visible=True,
            seller=""
        )
        result = classify_featured_offer(report, "Northwind")
        self.assertEqual(result["featured_offer_verdict"], VERDICT_NONE)

    def test_currently_unavailable(self):
        report = verified_report(
            add_to_basket_visible=False,
            buy_now_visible=False,
            availability="Currently unavailable.",
            seller=""
        )
        result = classify_featured_offer(report, "Northwind")
        self.assertEqual(result["featured_offer_verdict"], VERDICT_NONE)

    def test_buttons_but_no_seller_is_not_verified(self):
        result = classify_featured_offer(verified_report(seller=""), "Northwind")
        self.assertEqual(result["featured_offer_verdict"], VERDICT_NOT_VERIFIED)

    def test_non_gbp_price_is_not_verified(self):
        result = classify_featured_offer(verified_report(currency="PKR"), "Northwind")
        self.assertEqual(result["featured_offer_verdict"], VERDICT_NOT_VERIFIED)


class ReadBuyBoxFromPageTests(unittest.TestCase):

    def test_reads_real_page_shape(self):
        page = FakePage({
            "#desktop_buybox": [REAL_TEXT_MANAGED],
            "#add-to-cart-button": ["Add to basket"],
            "#buy-now-button": ["Buy Now"],
            "#corePrice_feature_div .a-offscreen": ["£19.99"],
            "#availability": ["In stock"],
            "#mir-layout-DELIVERY_BLOCK": ["FREE delivery Saturday, 14 November."],
        })
        location = {"verified": True, "security_challenge": False}

        report = read_buy_box_from_page(page, location, "Northwind")

        self.assertEqual(report["price"], "£19.99")
        self.assertEqual(report["currency"], "GBP")
        self.assertEqual(report["seller"], "Northwind")
        self.assertEqual(report["dispatches_from"], "Amazon")
        self.assertEqual(report["featured_offer_verdict"], VERDICT_YOURS)

    def test_nothing_is_read_when_location_not_verified(self):
        page = FakePage({"#desktop_buybox": [REAL_TEXT_MANAGED]})

        report = read_buy_box_from_page(page, {"verified": False}, "Northwind")

        self.assertEqual(report["seller"], "")
        self.assertEqual(report["featured_offer_verdict"], VERDICT_NOT_VERIFIED)


class SmallHelperTests(unittest.TestCase):

    def test_currency(self):
        self.assertEqual(detect_currency("£17.99"), "GBP")
        self.assertEqual(detect_currency("PKR 6,702.68"), "PKR")
        self.assertEqual(detect_currency(""), "")

    def test_seller_names_compare_loosely(self):
        self.assertEqual(normalise_seller(" Northwind. "), normalise_seller("northwind"))

    def test_company_ending_is_ignored(self):
        # Real case: saved "Northwind LTD", Amazon shows "Northwind".
        self.assertEqual(normalise_seller("Northwind LTD"), normalise_seller("Northwind"))
        self.assertEqual(normalise_seller("Northwind Limited"), normalise_seller("Northwind"))
        self.assertNotEqual(normalise_seller("Northwind Home"), normalise_seller("Northwind"))

    def test_real_case_northwind_ltd_is_yours(self):
        result = classify_featured_offer(verified_report(), "Northwind LTD")
        self.assertEqual(result["featured_offer_verdict"], VERDICT_YOURS)


if __name__ == "__main__":
    unittest.main()
