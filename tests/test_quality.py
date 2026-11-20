"""
Tests for listing quality rules, the issue report and the
load-next-product speed-up. No browser or internet needed.

Run from the project folder:
    python -m unittest discover -s tests -t . -v
"""

import unittest

from modules.quality_rules import (
    check_title,
    check_bullets,
    check_description,
    check_images,
    check_listing_quality,
)
from services.issue_report import (
    build_issue_rows,
    build_product_scorecard,
    batch_totals,
)
from modules import amazon_session


def rules(findings):
    return [finding["rule"] for finding in findings]


GOOD_BULLETS = [
    "Soft microfibre fabric that stays smooth after washing",
    "Machine washable at 40 degrees; quick to dry",
    "Includes one duvet cover and two pillowcases",
]


class TitleTests(unittest.TestCase):

    def test_clean_short_title_has_no_findings(self):
        self.assertEqual(check_title("Northwind Duvet Cover Set Double Grey"), [])

    def test_title_over_200_characters_is_high(self):
        findings = check_title("Duvet " * 40)
        self.assertIn("Title too long", rules(findings))
        self.assertEqual(findings[0]["severity"], "High")

    def test_title_over_80_is_only_advice(self):
        findings = check_title("Northwind Duvet Cover Set Double Grey Soft Brushed Microfibre Bedding With Pillowcases")
        self.assertEqual(rules(findings), ["Title longer than mobile view"])
        self.assertEqual(findings[0]["severity"], "Advice")

    def test_banned_characters(self):
        findings = check_title("Duvet Cover Set! Best $ Price?")
        banned = [f for f in findings if f["rule"] == "Special characters not allowed"][0]
        self.assertEqual(banned["found"], "! $ ?")

    def test_hyphen_and_brackets_are_allowed(self):
        self.assertEqual(check_title("Duvet Cover - Double (200 x 200 cm)"), [])

    def test_word_repeated_three_times(self):
        findings = check_title("Duvet Cover Duvet Set Duvet Grey")
        self.assertIn("Word repeated more than twice", rules(findings))

    def test_promotional_wording(self):
        self.assertIn("Promotional wording", rules(check_title("Duvet Cover Free Delivery")))

    def test_empty_title(self):
        self.assertEqual(rules(check_title("")), ["Title not found"])


class BulletTests(unittest.TestCase):

    def test_good_bullets_pass(self):
        self.assertEqual(check_bullets(GOOD_BULLETS), [])

    def test_too_few_bullets(self):
        self.assertIn("Too few bullet points", rules(check_bullets(GOOD_BULLETS[:2])))

    def test_special_characters_and_emoji(self):
        findings = check_bullets(GOOD_BULLETS + ["Premium® quality ✅ fabric for every bedroom"])
        self.assertIn("Special characters not allowed", rules(findings))
        self.assertIn("Emoji or decorative symbol", rules(findings))
        self.assertTrue(all(f["area"] == "Bullet 4" for f in findings))

    def test_guarantee_and_placeholder(self):
        findings = check_bullets(GOOD_BULLETS + ["Full refund if not satisfied", "Material: N/A for this item"])
        self.assertIn("Refund or guarantee wording", rules(findings))
        self.assertIn("Placeholder text", rules(findings))

    def test_duplicate_and_lowercase_start(self):
        findings = check_bullets(GOOD_BULLETS + ["soft microfibre fabric that stays smooth after washing"])
        self.assertIn("Duplicate bullet point", rules(findings))
        self.assertIn("Does not start with a capital letter", rules(findings))

    def test_asin_in_bullet(self):
        self.assertIn("ASIN in bullet point", rules(check_bullets(GOOD_BULLETS + ["Matches B0AAAAAA01 sheets"])))


class OtherRuleTests(unittest.TestCase):

    def test_description_not_needed_with_aplus(self):
        self.assertEqual(check_description("", aplus_displayed=True), [])
        self.assertEqual(len(check_description("", aplus_displayed=False)), 1)

    def test_images(self):
        self.assertEqual(check_images(None), [])
        self.assertEqual(check_images(0)[0]["severity"], "High")
        self.assertEqual(check_images(3)[0]["severity"], "Advice")
        self.assertEqual(check_images(7), [])

    def test_full_listing(self):
        content = {"title": "Northwind Duvet Cover Set", "bullets": GOOD_BULLETS, "description": "Soft."}
        self.assertEqual(check_listing_quality(content, 7, True), [])


def make_result(asin, verdict="HELD BY YOUR SELLER", quality=None, spec_issues=None,
                status="ISSUES FOUND", seconds=5.0):
    return {
        "asin": asin,
        "overall_status": status,
        "seconds": seconds,
        "buy_box": {
            "featured_offer_verdict": verdict,
            "seller": "Other Shop",
            "expected_seller": "Northwind LTD",
            "location": {"verified": True},
        },
        "content": {"title": "Duvet"},
        "quality": quality or [],
        "spelling": {"issues": [], "data_gaps": []},
        "spec_check": {"issues": spec_issues or []},
        "content_findings": [],
        "errors": [],
    }


class IssueReportTests(unittest.TestCase):

    def test_one_row_per_issue_with_asin(self):
        results = [
            make_result("B000000001", verdict="HELD BY ANOTHER SELLER"),
            make_result("B000000002", spec_issues=[{
                "location": "Product information: Item weight",
                "detected_term": "1.2 kg", "correct_term": "1.5 kg"
            }]),
        ]
        rows = build_issue_rows(results)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["ASIN"] for row in rows}, {"B000000001", "B000000002"})
        featured = [row for row in rows if row["Area"] == "Featured Offer"][0]
        self.assertEqual(featured["Amazon Shows"], "Other Shop")
        self.assertEqual(featured["Should Be"], "Northwind LTD")

    def test_high_issues_come_first(self):
        results = [
            make_result("B000000001", quality=[{"area": "Bullet 1", "rule": "x", "severity": "Low"}]),
            make_result("B000000002", verdict="NO FEATURED OFFER"),
        ]
        rows = build_issue_rows(results)
        self.assertEqual(rows[0]["Severity"], "High")

    def test_scorecard_verdicts(self):
        results = [
            make_result("B000000001"),
            make_result("B000000002", verdict="HELD BY ANOTHER SELLER"),
            make_result("B000000003", quality=[{"area": "Title", "rule": "x", "severity": "Medium"}]),
            make_result("B000000004", status="LOCATION NOT VERIFIED"),
        ]
        card = {row["ASIN"]: row["Result"] for row in build_product_scorecard(results)}
        self.assertTrue(card["B000000001"].startswith("✅"))
        self.assertTrue(card["B000000002"].startswith("❌"))
        self.assertTrue(card["B000000003"].startswith("🟠"))
        self.assertTrue(card["B000000004"].startswith("⚠️"))

    def test_totals(self):
        totals = batch_totals([make_result("B000000001", seconds=4.0),
                               make_result("B000000002", verdict="NO FEATURED OFFER", seconds=6.0)])
        self.assertEqual(totals["products"], 2)
        self.assertEqual(totals["fix_now"], 1)
        self.assertEqual(totals["average_seconds"], 5.0)


# ---------- load-next-product speed-up ----------

class FakeLocator:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    @property
    def first(self):
        return self

    def count(self):
        if "captcha" in self.selector.lower():
            return 0
        return 1 if "productTitle" in self.selector or "glow" in self.selector else 0

    def inner_text(self, timeout=None):
        return "Deliver to London SW1A 1AA"


class FakeResponse:
    status = 200


class FakePage:
    def __init__(self, name):
        self.name, self.closed, self.visited = name, False, []

    def goto(self, url, wait_until=None, timeout=None):
        self.visited.append((url, wait_until))
        return FakeResponse()

    def wait_for_selector(self, selector, timeout=None):
        return None

    def wait_for_timeout(self, ms):
        return None

    def title(self):
        return "Product " + self.name

    def locator(self, selector):
        return FakeLocator(self, selector)

    def reload(self, **kwargs):
        return None

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self):
        self.made = []

    def new_page(self):
        page = FakePage(f"tab{len(self.made) + 1}")
        self.made.append(page)
        return page


class PrefetchTests(unittest.TestCase):

    def setUp(self):
        self._mark = amazon_session.mark_location_verified
        amazon_session.mark_location_verified = lambda *args: None

        browser = object.__new__(amazon_session.AmazonBrowser)
        browser.postcode = "SW1A 1AA"
        browser.context = FakeContext()
        browser.page = FakePage("main")
        browser.prompted = False
        browser.prefetched = {}
        browser.next_url = None
        browser.extra_tab = None
        browser.upcoming = []
        browser.auto_set_tried = False
        self.browser = browser

    def tearDown(self):
        amazon_session.mark_location_verified = self._mark

    def test_next_product_starts_loading_and_is_reused(self):
        browser = self.browser

        browser.next_url = "https://www.amazon.co.uk/dp/B000000002"
        page, report = browser.open_product("https://www.amazon.co.uk/dp/B000000001")

        self.assertIs(page, browser.page)
        self.assertTrue(report["verified"])
        self.assertIn("https://www.amazon.co.uk/dp/B000000002", browser.prefetched)

        tab = browser.context.made[0]
        self.assertEqual(tab.visited[0][1], "commit")

        browser.next_url = None
        page2, report2 = browser.open_product("https://www.amazon.co.uk/dp/B000000002")

        self.assertIs(page2, tab)
        self.assertTrue(report2["verified"])
        self.assertEqual(len(browser.context.made), 1)

        # The extra tab is closed when the following product opens.
        browser.open_product("https://www.amazon.co.uk/dp/B000000003")
        self.assertTrue(tab.closed)


if __name__ == "__main__":
    unittest.main()
