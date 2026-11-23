"""Parent-level A+ / Brand Story check (no browser)."""

import unittest

from services.family_checks import apply_family_checks
from services.issue_report import build_product_scorecard


def product(asin, aplus, parent="P000000001"):
    return {
        "asin": asin, "parent_asin": parent, "overall_status": "NO RULE-BASED ISSUES FOUND",
        "content_display": {"aplus": {"status": aplus}, "brand_story": {"status": "NOT DISPLAYED"}},
        "content_findings": [], "buy_box": {"featured_offer_verdict": "HELD BY YOUR SELLER"},
    }


class FamilyTests(unittest.TestCase):

    def test_no_aplus_anywhere_is_not_an_error(self):
        results = apply_family_checks([product("B1", "NOT DISPLAYED"), product("B2", "NOT DISPLAYED")])
        self.assertTrue(all(not r["content_findings"] for r in results))
        self.assertTrue(all(r["overall_status"] == "NO RULE-BASED ISSUES FOUND" for r in results))

    def test_missing_where_family_has_it(self):
        results = apply_family_checks([product("B1", "DISPLAYED"), product("B2", "NOT DISPLAYED")])
        self.assertEqual(results[0]["content_findings"], [])
        self.assertEqual(results[1]["content_findings"][0]["Item"], "A+ content (EBC)")
        self.assertEqual(results[1]["overall_status"], "ISSUES FOUND")
        card = build_product_scorecard(results)
        self.assertIn("A+ content (EBC): Not shown → should be Shown, like B1", card[1]["What's Wrong"])

    def test_parents_are_judged_separately(self):
        results = apply_family_checks([
            product("B1", "DISPLAYED", "P1"), product("B2", "NOT DISPLAYED", "P2"),
        ])
        self.assertEqual(results[1]["content_findings"], [])

    def test_buy_box_column(self):
        card = build_product_scorecard([product("B1", "DISPLAYED")])
        self.assertEqual(card[0]["Buy Box"], "✅ Yes (yours)")


if __name__ == "__main__":
    unittest.main()
