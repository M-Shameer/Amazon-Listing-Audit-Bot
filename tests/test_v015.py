"""
Tests for version 0.15: text check columns, collapsed product
information, one-row-per-product results and copy-to-Excel text.
No browser or internet needed.
"""

import unittest

from modules.spec_checker import (
    check_against_spec,
    check_text_column,
    text_check_parts,
    RESULT_MATCH,
    RESULT_MISMATCH,
    RESULT_NOT_SHOWN,
)
from services.issue_report import (
    build_issue_rows,
    build_product_scorecard,
    not_checked_summary,
    rows_to_tsv,
)
from tests.test_quality import make_result


LISTING = {
    "title": "Brightbed 400 Thread Count Duvet Cover Set King",
    "bullets": ["100% Egyptian Cotton, soft and breathable", "Oeko-Tex certified"],
    "description": "Luxury sateen weave.",
}


class TextColumnTests(unittest.TestCase):

    def test_column_names(self):
        self.assertEqual(text_check_parts("Description contains"), ("description",))
        self.assertEqual(text_check_parts("listing CONTAINS"), ("title", "bullets", "description"))
        self.assertEqual(text_check_parts("Fabric Type"), ())

    def test_phrase_found_ignoring_case_and_spaces(self):
        result, shows, _ = check_text_column("100%  egyptian cotton", ("bullets",), LISTING)
        self.assertEqual(result, RESULT_MATCH)

    def test_spelling_must_match(self):
        result, shows, _ = check_text_column("100% Egyptain Cotton", ("bullets",), LISTING)
        self.assertEqual(result, RESULT_MISMATCH)
        self.assertIn("Egyptain", shows)

    def test_several_phrases(self):
        result, shows, _ = check_text_column("Oeko-Tex; Sateen; Silk", ("bullets", "description"), LISTING)
        self.assertEqual(result, RESULT_MISMATCH)
        self.assertEqual(shows, "Not found: Silk")

    def test_unread_text(self):
        result, _, _ = check_text_column("anything", ("description",), {"description": ""})
        self.assertEqual(result, RESULT_NOT_SHOWN)

    def test_in_full_spec_check(self):
        spec = {"set_name": "Duvets", "product_type": "Duvet Cover Set", "rows": [{
            "product_type": "Duvet Cover Set", "size": "King Pack of 4",
            "values": {"Fabric Type": "100% Egyptian Cotton",
                       "Title contains": "400 Thread Count",
                       "Description contains": "Percale weave"},
        }]}
        technical = {"Size": "King (220 x 230 cm) - Pack of 4", "Fabric Type": "100% Egyptian Cotton"}
        report = check_against_spec(technical, spec, dict(LISTING, selections={}))
        results = {row["Field"]: row["Result"] for row in report["rows"]}
        self.assertEqual(results["Fabric Type"], RESULT_MATCH)
        self.assertEqual(results["Title contains"], RESULT_MATCH)
        self.assertEqual(results["Description contains"], RESULT_MISMATCH)
        self.assertEqual(report["issues"][0]["location"], "Listing text: Description contains")


class NewLayoutTests(unittest.TestCase):

    def test_screenshot_values_pick_the_pack_row(self):
        # Values from the Product information screenshot (B0AAAAAA05).
        spec = {"set_name": "Duvets", "product_type": "Duvet Cover Set", "rows": [
            {"product_type": "Duvet Cover Set", "size": "King Pack of 2", "values": {"Thread Count": "400"}},
            {"product_type": "Duvet Cover Set", "size": "King Pack of 4", "values": {"Thread Count": "400"}},
        ]}
        technical = {"Size": "King (220 x 230 cm) - Pack of 4", "Number of Pieces": "12",
                     "Number of Items": "2", "Unit Count": "1.0 count", "Thread Count": "400"}
        report = check_against_spec(technical, spec)
        self.assertEqual(report["template_size"], "King Pack of 4")


class ResultsLayoutTests(unittest.TestCase):

    def location_failure(self, asin):
        result = make_result(asin, status="LOCATION NOT VERIFIED")
        result["buy_box"]["location"] = {"verified": False, "amazon_header": "Pakistan",
                                         "saved_postcode": "SW1A 1AA"}
        result["buy_box"]["featured_offer_verdict"] = "NOT VERIFIED"
        result["errors"] = ["Amazon is not using your saved postcode. A long message..."]
        return result

    def test_not_checked_product_gets_one_short_row(self):
        rows = build_issue_rows([self.location_failure("B000000001")])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Area"], "Not checked")
        self.assertEqual(rows[0]["Amazon Shows"], "Pakistan")

    def test_summary_of_not_checked(self):
        results = [self.location_failure("B000000001"), self.location_failure("B000000002"),
                   make_result("B000000003")]
        self.assertEqual(not_checked_summary(results),
                         {"LOCATION NOT VERIFIED": ["B000000001", "B000000002"]})

    def test_one_row_per_asin_with_all_issues(self):
        result = make_result(
            "B000000001", verdict="HELD BY ANOTHER SELLER",
            quality=[{"area": "Title", "rule": "Special characters not allowed", "found": "!",
                      "expected": "None", "severity": "High", "action": "x"}],
        )
        card = build_product_scorecard([result])
        self.assertEqual(len(card), 1)
        # The Buy Box has its own column; What's Wrong lists only errors.
        self.assertEqual(card[0]["Buy Box"], "❌ Lost to " + (result["buy_box"].get("seller") or "another seller"))
        self.assertNotIn("Featured Offer", card[0]["What's Wrong"])
        self.assertIn("Title: Special characters not allowed (! → should be removed)", card[0]["What's Wrong"])

    def test_spec_issue_is_short(self):
        result = make_result("B000000001")
        result["spec_check"] = {"status": "CHECKED", "issues": [{
            "location": "Product information: Number of Pieces", "detected_term": "2",
            "correct_term": "4"}]}
        card = build_product_scorecard([result])
        self.assertIn("• Number of Pieces: 2 → should be 4", card[0]["What's Wrong"])

    def test_tsv_pastes_into_excel_columns(self):
        text = rows_to_tsv([{"ASIN": "B1", "Issue": "a\tb"}, {"ASIN": "B2", "Issue": "c\nd"}])
        lines = text.split("\n")
        self.assertEqual(lines[0], "ASIN\tIssue")
        self.assertEqual(lines[1], "B1\ta b")
        self.assertEqual(lines[2], "B2\tc d")


if __name__ == "__main__":
    unittest.main()
