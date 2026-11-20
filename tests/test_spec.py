"""
Tests for the specification template and checker.

No browser and no Amazon: the Amazon values below are copied from a
real audit of B0AAAAAA01.

Run from the project folder:
    python -m unittest discover -s tests -t . -v
"""

import unittest
from io import BytesIO

from openpyxl import load_workbook

from modules.spec_checker import (
    compare_value,
    read_measure,
    find_size_row,
    check_against_spec,
    RESULT_MATCH,
    RESULT_CHECK,
    RESULT_MISMATCH,
    RESULT_NOT_SHOWN,
    STATUS_CHECKED,
    STATUS_NO_SIZE,
    STATUS_ROW_EMPTY,
)
from services.spec_service import (
    build_blank_template,
    parse_template,
    build_spec_for_audit,
    SHEET_NAME,
)


# Real Product information from B0AAAAAA01 (shortened).
AMAZON_DETAILS = {
    "Number of Pieces": "3",
    "Included Components": "Duvet Cover Set (1 x Duvet Cover + 2 x Pillowcases)",
    "Size": "Double (200 x 200 cm) - 3 Piece",
    "Item Dimensions": "200 x 200 x 5 centimetres",
    "Pillowcase Width": "50 Centimetres",
    "Pillowcase Length": "75 Centimetres",
    "Colour": "Gray",
    "Material Type": "Microfibre",
    "Thread Count": "200",
    "Fabric Type": "100% Premium Microfiber",
    "Closure Type": "Zipper",
}


class CompareValueTests(unittest.TestCase):

    def test_same_text(self):
        self.assertEqual(compare_value("Zipper", "zipper")[0], RESULT_MATCH)

    def test_units_are_converted(self):
        self.assertEqual(compare_value("50 cm", "50 Centimetres")[0], RESULT_MATCH)
        self.assertEqual(compare_value("1.2 kg", "1200 Grams")[0], RESULT_MATCH)
        self.assertEqual(compare_value("500 mm", "50 cm")[0], RESULT_MATCH)

    def test_wrong_number(self):
        self.assertEqual(compare_value("75 cm", "70 Centimetres")[0], RESULT_MISMATCH)

    def test_extra_depth_needs_checking(self):
        # Template gives 200 x 200, Amazon adds a third number (5).
        self.assertEqual(
            compare_value("200 x 200 cm", "200 x 200 x 5 centimetres")[0],
            RESULT_CHECK
        )

    def test_spelling_difference_is_mismatch(self):
        self.assertEqual(
            compare_value("100% Microfibre", "100% Premium Microfiber")[0],
            RESULT_MISMATCH
        )

    def test_extra_words_need_checking(self):
        self.assertEqual(
            compare_value("100% Microfibre", "100% Premium Microfibre")[0],
            RESULT_CHECK
        )

    def test_length_vs_weight_is_mismatch(self):
        self.assertEqual(compare_value("200 g", "200 cm")[0], RESULT_MISMATCH)

    def test_missing_on_amazon(self):
        self.assertEqual(compare_value("1.5 kg", "")[0], RESULT_NOT_SHOWN)

    def test_read_measure(self):
        self.assertEqual(read_measure("200 x 200 x 5 centimetres"), ([200.0, 200.0, 5.0], "length"))
        self.assertEqual(read_measure("1.2 kg"), ([1200.0], "weight"))


class SizeMatchingTests(unittest.TestCase):

    ROWS = [
        {"size": "King"},
        {"size": "Super King"},
        {"size": "Double"},
    ]

    def test_double_matches_amazon_text(self):
        row = find_size_row(self.ROWS, "Double (200 x 200 cm) - 3 Piece")
        self.assertEqual(row["size"], "Double")

    def test_king_does_not_match_super_king(self):
        row = find_size_row(self.ROWS, "Super King (260 x 220 cm)")
        self.assertEqual(row["size"], "Super King")

    def test_unknown_size(self):
        self.assertIsNone(find_size_row(self.ROWS, "Single (135 x 200 cm)"))


class CheckAgainstSpecTests(unittest.TestCase):

    SPEC = {
        "set_name": "Test Set",
        "product_type": "Duvet Cover Set",
        "rows": [{
            "product_type": "Duvet Cover Set",
            "size": "Double",
            "values": {
                "Number of Pieces": "3",
                "Item Dimensions": "200 x 200 cm",
                "Pillowcase Width": "50 cm",
                "Pillowcase Length": "75 cm",
                "Thread Count": "200",
                "Fabric Type": "100% Microfibre",
                "Item Weight": "1.1 kg",
                "Closure Type": "",          # empty = not checked
            }
        }]
    }

    def test_real_listing(self):
        report = check_against_spec(AMAZON_DETAILS, self.SPEC)

        self.assertEqual(report["status"], STATUS_CHECKED)
        self.assertEqual(report["template_size"], "Double")

        results = {row["Field"]: row["Result"] for row in report["rows"]}

        self.assertEqual(results["Number of Pieces"], RESULT_MATCH)
        self.assertEqual(results["Pillowcase Width"], RESULT_MATCH)
        self.assertEqual(results["Thread Count"], RESULT_MATCH)
        self.assertEqual(results["Item Dimensions"], RESULT_CHECK)
        self.assertEqual(results["Fabric Type"], RESULT_MISMATCH)
        self.assertEqual(results["Item Weight"], RESULT_NOT_SHOWN)
        self.assertNotIn("Closure Type", results)

        # Only real mismatches become issues.
        self.assertEqual(len(report["issues"]), 1)
        self.assertIn("Fabric Type", report["issues"][0]["location"])

    def test_empty_template_row(self):
        # Real case: values typed on the Single row, audited a Double.
        spec = {"set_name": "S", "product_type": "Duvet Cover Set", "rows": [
            {"product_type": "Duvet Cover Set", "size": "Single",
             "values": {"Thread Count": "200"}},
            {"product_type": "Duvet Cover Set", "size": "Double",
             "values": {"Thread Count": ""}},
        ]}
        report = check_against_spec(AMAZON_DETAILS, spec)
        self.assertEqual(report["status"], STATUS_ROW_EMPTY)
        self.assertEqual(report["template_size"], "Double")

    def test_size_not_in_template(self):
        details = dict(AMAZON_DETAILS, Size="Single (135 x 200 cm)")
        report = check_against_spec(details, self.SPEC)
        self.assertEqual(report["status"], STATUS_NO_SIZE)
        self.assertEqual(report["issues"], [])


class TemplateFileTests(unittest.TestCase):

    def test_blank_template_reads_back(self):
        parsed = parse_template(build_blank_template())

        self.assertEqual(parsed["errors"], [])
        self.assertIn("Item Weight", parsed["fields"])
        self.assertEqual(len(parsed["rows"]), 8)   # 2 types x 4 sizes

    def test_filled_template_and_audit_spec(self):
        workbook = load_workbook(BytesIO(build_blank_template()))
        sheet = workbook[SHEET_NAME]

        headers = [cell.value for cell in sheet[1]]
        sheet.cell(row=3, column=headers.index("Thread Count") + 1, value=200)  # Duvet / Double
        sheet.cell(row=20, column=1, value="Duvet Cover Set")                    # duplicate row
        sheet.cell(row=20, column=2, value="Double")
        sheet.cell(row=20, column=5, value="x")

        buffer = BytesIO()
        workbook.save(buffer)

        parsed = parse_template(buffer.getvalue())

        double = next(row for row in parsed["rows"] if row["size"] == "Double"
                      and row["product_type"] == "Duvet Cover Set")
        self.assertEqual(double["values"]["Thread Count"], "200")
        self.assertTrue(any("appears twice" in warning for warning in parsed["warnings"]))

        spec = build_spec_for_audit({"name": "Mine", "data": parsed}, "Fitted Sheet")
        self.assertEqual(len(spec["rows"]), 4)
        self.assertTrue(all(row["product_type"] == "Fitted Sheet" for row in spec["rows"]))

    def test_wrong_file_is_rejected(self):
        parsed = parse_template(b"not an excel file")
        self.assertTrue(parsed["errors"])


if __name__ == "__main__":
    unittest.main()
