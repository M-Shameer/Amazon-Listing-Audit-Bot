"""
Tests for building a specification template from a live listing family.
No browser or internet needed (audit results are made up).
"""

import unittest

from services.template_builder import (
    size_label,
    choose_items,
    build_template_rows,
    build_template_workbook,
)
from services.spec_service import parse_template
from modules.spec_checker import check_against_spec, RESULT_MATCH, RESULT_MISMATCH


ROWS = [
    {"asin": "B0AAAAAA01", "colour": "Grey", "size": "Single (135 x 200 cm)"},
    {"asin": "B0AAAAAA02", "colour": "Blue", "size": "Single (135 x 200 cm)"},
    {"asin": "B0AAAAAA03", "colour": "Pink", "size": "Single (135 x 200 cm)"},
    {"asin": "B0AAAAAA04", "colour": "Sage", "size": "Single (135 x 200 cm)"},
    {"asin": "B0AAAAAA05", "colour": "Grey", "size": "King (220 x 230 cm) - Pack of 2"},
]


def result(asin, **details):
    return {"asin": asin, "content": {"technical_details": dict(details, ASIN=asin)}}


SINGLE = {
    "Size": "Single (135 x 200 cm)", "Colour": "Grey", "Thread Count": "300",
    "Item Dimensions": "2 x 1.35 x 0.03 metres", "Material Type": "Polyester",
    "Customer Reviews": "4.5 out of 5 stars",
}


class LabelTests(unittest.TestCase):

    def test_size_labels(self):
        self.assertEqual(size_label("Single (135 x 200 cm)"), "Single")
        self.assertEqual(size_label("King (220 x 230 cm) - Pack of 2"), "King Pack of 2")
        self.assertEqual(size_label("Double 4 Piece Set"), "Double 4 Piece")
        self.assertEqual(size_label("SKing (260 x 220 cm)"), "Super King")


class ChooseTests(unittest.TestCase):

    def test_three_colours_per_size_by_default(self):
        items = choose_items(ROWS)
        self.assertEqual([item["asin"] for item in items],
                         ["B0AAAAAA01", "B0AAAAAA02", "B0AAAAAA03", "B0AAAAAA05"])

    def test_only_chosen_sizes(self):
        items = choose_items(ROWS, 1, ["King (220 x 230 cm) - Pack of 2"])
        self.assertEqual([item["asin"] for item in items], ["B0AAAAAA05"])


class BuildTests(unittest.TestCase):

    def build(self):
        items = choose_items(ROWS)
        results = [
            result("B0AAAAAA01", **SINGLE, **{"Item Weight": "1.2 Kilograms"}),
            result("B0AAAAAA02", **dict(SINGLE, Colour="Blue"), **{"Item Weight": "1.2 Kilograms"}),
            result("B0AAAAAA03", **dict(SINGLE, Colour="Pink"), **{"Item Weight": "1.5 Kilograms"}),
            {"asin": "B0AAAAAA05", "content": {}},
        ]
        return build_template_rows(results, items, "Duvet Cover Set")

    def test_one_row_per_size_with_majority_values(self):
        rows, notes, unread = self.build()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["size"], "Single")
        self.assertEqual(rows[0]["values"]["Item Weight"], "1.2 Kilograms")
        self.assertEqual(rows[0]["values"]["Thread Count"], "300")

    def test_listing_specific_fields_left_out(self):
        rows, _, _ = self.build()
        for field in ("ASIN", "Colour", "Size", "Customer Reviews"):
            self.assertNotIn(field, rows[0]["values"])

    def test_odd_colour_is_noted(self):
        _, notes, _ = self.build()
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["Field"], "Item Weight")
        self.assertIn("B0AAAAAA03: 1.5 Kilograms", notes[0]["Other values"])

    def test_unread_pages_are_reported(self):
        _, _, unread = self.build()
        self.assertEqual(unread, ["B0AAAAAA05"])

    def test_workbook_uploads_and_finds_the_odd_colour(self):
        rows, notes, _ = self.build()
        parsed = parse_template(build_template_workbook(rows, notes, "ES-DCS"))
        self.assertEqual(parsed["errors"], [])
        self.assertEqual(parsed["rows"][0]["size"], "Single")

        spec = {"set_name": "ES-DCS", "product_type": "Duvet Cover Set", "rows": parsed["rows"]}
        good = check_against_spec(dict(SINGLE, **{"Item Weight": "1.2 Kilograms"}), spec)
        odd = check_against_spec(dict(SINGLE, **{"Item Weight": "1.5 Kilograms"}), spec)

        weight = lambda report: next(r["Result"] for r in report["rows"] if r["Field"] == "Item Weight")
        self.assertEqual(weight(good), RESULT_MATCH)
        self.assertEqual(weight(odd), RESULT_MISMATCH)


if __name__ == "__main__":
    unittest.main()
