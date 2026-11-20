"""
Tests that every kind of finding is saved, tracked and rechecked.
Uses a temporary database file, never your real audit history.
"""

import os
import tempfile
import unittest
from pathlib import Path

from database import db
from services import history_service as history
from tests.test_quality import make_result


SPEC_ISSUE = {
    "location": "Product information: Item Weight",
    "detected_term": "1.2 kg", "correct_term": "1.5 kg",
}

TITLE_FINDING = {
    "area": "Title", "rule": "Special characters not allowed", "found": "!",
    "expected": "None", "severity": "High", "action": "Remove it.",
}


class TrackingTests(unittest.TestCase):

    def setUp(self):
        self._path = db.DB_PATH
        folder = tempfile.mkdtemp()
        db.DB_PATH = Path(folder) / "test.db"

    def tearDown(self):
        db.DB_PATH = self._path

    def test_all_kinds_are_tracked(self):
        result = make_result(
            "B000000001", verdict="HELD BY ANOTHER SELLER",
            quality=[TITLE_FINDING], spec_issues=[SPEC_ISSUE]
        )
        issues = history.trackable_issues(result)
        problems = {issue["category"] for issue in issues}
        self.assertIn("High | Another seller holds the Featured Offer (Buy Box)", problems)
        self.assertIn("High | Special characters not allowed", problems)
        self.assertIn("High | Does not match your specification", problems)

    def test_fingerprint_ignores_which_seller(self):
        first = make_result("B000000001", verdict="HELD BY ANOTHER SELLER")
        second = make_result("B000000001", verdict="HELD BY ANOTHER SELLER")
        second["buy_box"]["seller"] = "A Different Shop"
        self.assertEqual(
            history.trackable_issues(first)[0]["fingerprint"],
            history.trackable_issues(second)[0]["fingerprint"],
        )

    def test_save_recheck_and_tracker(self):
        before = make_result("B000000001", quality=[TITLE_FINDING], spec_issues=[SPEC_ISSUE])
        run_id = history.save_run("New Audit", "", [before], [])

        tracker = history.get_all_issues_with_status()
        self.assertEqual(len(tracker), 2)
        self.assertTrue(all(issue["status"] == "Not Started" for issue in tracker))

        # Title fixed; recheck WITHOUT the specification set.
        after = make_result("B000000001")
        rows = history.compare_recheck_against_run(
            run_id, "B000000001", history.trackable_issues(after), True, checks_run=set()
        )
        outcome = {row["Issue"]: row["Recheck Result"] for row in rows}

        self.assertEqual(outcome["Title"], "VERIFIED FIXED")
        # The spec check did not run, so it must NOT be called fixed.
        self.assertEqual(outcome["Product information: Item Weight"], "NOT CHECKED THIS TIME")

        statuses = {issue["location"]: issue["status"] for issue in history.get_all_issues_with_status()}
        self.assertEqual(statuses["Title"], "Verified Fixed")
        self.assertEqual(statuses["Product information: Item Weight"], "Not Started")

    def test_still_present_with_spec(self):
        before = make_result("B000000001", spec_issues=[SPEC_ISSUE])
        run_id = history.save_run("New Audit", "", [before], [])

        rows = history.compare_recheck_against_run(
            run_id, "B000000001", history.trackable_issues(before), True, checks_run={"spec"}
        )
        self.assertEqual(rows[0]["Recheck Result"], "STILL PRESENT")
        self.assertEqual(history.get_all_issues_with_status()[0]["status"], "Still Present")

    def test_failed_read_is_never_fixed(self):
        before = make_result("B000000001", quality=[TITLE_FINDING])
        run_id = history.save_run("New Audit", "", [before], [])
        rows = history.compare_recheck_against_run(run_id, "B000000001", [], False)
        self.assertEqual(rows[0]["Recheck Result"], "NOT VERIFIED - product not read")


if __name__ == "__main__":
    unittest.main()
