"""
Tests for fitted sheets and other parts of a set, templates with several
sheets, and the measurement fixes (size names, order, kg / g).
No browser or internet needed.
"""

import unittest
from io import BytesIO

from openpyxl import Workbook

from modules.spec_checker import (
    compare_value,
    check_against_spec,
    find_in_listing_text,
    text_anchors,
    RESULT_MATCH,
    RESULT_CHECK,
    RESULT_MISMATCH,
)
from services.spec_service import parse_template


LISTING = {
    "title": "Brightbed 4 Piece Duvet Cover Set King",
    "bullets": [
        "Includes 1 duvet cover 220 x 230 cm, 1 fitted sheet 150 x 200 cm "
        "with 35cm deep pockets and 2 pillowcases 50 x 75 cm",
    ],
    "description": "",
}


class MeasurementTests(unittest.TestCase):

    def test_size_name_in_item_dimensions(self):
        self.assertEqual(compare_value("King (220 x 230 cm)", "220 x 230 cm")[0], RESULT_MATCH)

    def test_other_order_and_depth_is_not_a_mismatch(self):
        self.assertEqual(compare_value("King (220 x 230 cm)", "2.3 x 2.2 x 0.04 metres")[0], RESULT_CHECK)

    def test_really_different_dimensions(self):
        self.assertEqual(compare_value("King (220 x 230 cm)", "2.0 x 2.0 x 0.04 metres")[0], RESULT_MISMATCH)

    def test_grams_meant_as_kilograms(self):
        result, note = compare_value("0.53G", "530 Grams")
        self.assertEqual(result, RESULT_CHECK)
        self.assertIn("kg", note)
        self.assertEqual(compare_value("0.53 kg", "530 Grams")[0], RESULT_MATCH)


class ListingTextTests(unittest.TestCase):

    def test_anchors(self):
        self.assertEqual(text_anchors("Fitted Sheet Pocket Depth"), ["pocket", "deep"])
        self.assertEqual(text_anchors("Fitted Sheet Dimensions"), ["fitted sheet"])

    def test_fitted_sheet_found(self):
        self.assertEqual(find_in_listing_text("Fitted Sheet Dimensions", "150 x 200 cm", LISTING)[0], RESULT_MATCH)
        self.assertEqual(find_in_listing_text("Fitted Sheet Pocket Depth", "35 Centimetres", LISTING)[0], RESULT_MATCH)

    def test_wrong_fitted_sheet_shows_its_own_measurement(self):
        result, shows, _ = find_in_listing_text("Fitted Sheet Dimensions", "180 x 200 cm", LISTING)
        self.assertEqual(result, RESULT_MISMATCH)
        self.assertIn("150 x 200 cm", shows)

    def test_not_written_anywhere(self):
        self.assertIsNone(find_in_listing_text("Flat Sheet Dimensions", "230 x 260 cm", LISTING))

    def test_in_full_spec_check_for_a_4_piece_set(self):
        spec = {"set_name": "Sets", "product_type": "Duvet Cover Set", "rows": [{
            "product_type": "Duvet Cover Set", "size": "King 4 PIECE",
            "values": {"Item Dimensions": "King (220 x 230 cm)",
                       "Fitted Sheet Dimensions": "150 x 200 cm",
                       "Fitted Sheet Pocket Depth": "40 cm"},
        }]}
        technical = {"Size": "King", "Number of Pieces": "4", "Item Dimensions": "220 x 230 cm"}
        report = check_against_spec(technical, spec, dict(LISTING, selections={}))
        results = {row["Field"]: row["Result"] for row in report["rows"]}
        self.assertEqual(report["template_size"], "King 4 PIECE")
        self.assertEqual(results["Item Dimensions"], RESULT_MATCH)
        self.assertEqual(results["Fitted Sheet Dimensions"], RESULT_MATCH)
        self.assertEqual(results["Fitted Sheet Pocket Depth"], RESULT_MISMATCH)
        self.assertEqual(report["issues"][0]["location"], "Listing text: Fitted Sheet Pocket Depth")


def workbook_bytes():
    book = Workbook()
    fitted = book.active
    fitted.title = "Specifications"
    fitted.append(["Product Type", "Size", "Item Weight", "Fitted Sheet Pocket Depth"])
    fitted.append(["Duvet Cover Set", "King", None, None])          # empty here
    fitted.append(["Fitted Sheet", "King", "0.56G", "35 Centimetres"])

    duvets = book.create_sheet("DCS Specifications")
    duvets.append(["Product Type", "Size", "Item Weight", "Fitted Sheet Pocket Depth"])
    duvets.append(["Duvet Cover Set", "King", "0.971 kg", None])      # filled here
    duvets.append(["Duvet Cover Set", "King 4 PIECE", None, "35 Centimetres"])

    links = book.create_sheet("Cotton-Fitted Sheet")
    links.append(["SINGLE", "DOUBLE"])
    links.append(["https://www.amazon.co.uk/dp/B0AAAAAA01", "https://www.amazon.co.uk/dp/B0AAAAAA02"])

    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


class TemplateSheetsTests(unittest.TestCase):

    def test_every_sheet_with_product_type_and_size_is_read(self):
        parsed = parse_template(workbook_bytes())
        self.assertEqual(parsed["errors"], [])
        keys = {(row["product_type"], row["size"]) for row in parsed["rows"]}
        self.assertEqual(keys, {("Duvet Cover Set", "King"), ("Fitted Sheet", "King"),
                                ("Duvet Cover Set", "King 4 PIECE")})

    def test_filled_row_replaces_empty_row(self):
        parsed = parse_template(workbook_bytes())
        king = next(row for row in parsed["rows"]
                    if row["product_type"] == "Duvet Cover Set" and row["size"] == "King")
        self.assertEqual(king["values"]["Item Weight"], "0.971 kg")

    def test_grams_warning(self):
        warnings = " ".join(parse_template(workbook_bytes())["warnings"])
        self.assertIn("'0.56G' means 0.56 GRAMS", warnings)
        self.assertNotIn("0.971", warnings)


if __name__ == "__main__":
    unittest.main()
