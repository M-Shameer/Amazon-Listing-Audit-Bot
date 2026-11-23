"""
Tests for variation-aware template matching: size + pieces + pack.
No browser or internet needed.
"""

import unittest

from modules.spec_checker import (
    variant_tokens,
    amazon_variant_tokens,
    find_size_row,
    check_against_spec,
    STATUS_CHECKED,
    STATUS_NO_SIZE,
)


def rows(*sizes):
    return [{"product_type": "Duvet Cover Set", "size": size, "values": {"Item Weight": "1 kg"}}
            for size in sizes]


def pick(template_rows, technical, selections=None, title=""):
    tokens = amazon_variant_tokens(technical, {"selections": selections or {}, "title": title})
    row = find_size_row(template_rows, technical.get("Size", ""), tokens)
    return row["size"] if row else None


DUVET_ROWS = rows("Single 3 Piece", "Double 4 Piece", "King 4 Piece", "SKing 4 Piece")

PACK_ROWS = rows(
    "Single Pack of 2", "Single Pack of 4", "Single Pack of 6",
    "Double Pack of 2", "Double Pack of 4", "Double Pack of 6",
    "Double",
)


class TokenTests(unittest.TestCase):

    def test_sizes_pieces_packs(self):
        self.assertEqual(variant_tokens("SKing 4 Piece"), {"superking", "pieces:4"})
        self.assertEqual(variant_tokens("Super King 4pcs"), {"superking", "pieces:4"})
        self.assertEqual(variant_tokens("Double - Pack of 2"), {"double", "pack:2"})
        self.assertEqual(variant_tokens("King 6 Pack"), {"king", "pack:6"})

    def test_dimensions_are_not_packs(self):
        self.assertEqual(variant_tokens("Double (200 x 200 cm)"), {"double"})


class DuvetPieceTests(unittest.TestCase):

    def test_size_and_style_fields(self):
        self.assertEqual(pick(DUVET_ROWS, {"Size": "Double", "Style": "4 Piece"}), "Double 4 Piece")

    def test_pieces_from_number_of_pieces(self):
        self.assertEqual(pick(DUVET_ROWS, {"Size": "Single", "Number of Pieces": "3"}), "Single 3 Piece")

    def test_super_king_never_matches_king(self):
        self.assertEqual(pick(DUVET_ROWS, {"Size": "Super King", "Number of Pieces": "4"}), "SKing 4 Piece")
        self.assertEqual(pick(DUVET_ROWS, {"Size": "King", "Number of Pieces": "4"}), "King 4 Piece")

    def test_selected_variation_buttons(self):
        self.assertEqual(
            pick(DUVET_ROWS, {}, selections={"size_name": "King", "style_name": "4 Piece Set"}),
            "King 4 Piece"
        )

    def test_wrong_piece_count_does_not_match(self):
        self.assertIsNone(pick(DUVET_ROWS, {"Size": "Double", "Number of Pieces": "3"}))

    def test_pieces_unknown_does_not_guess(self):
        self.assertIsNone(pick(DUVET_ROWS, {"Size": "Double"}))


class PackTests(unittest.TestCase):

    def test_pack_from_size_text(self):
        self.assertEqual(pick(PACK_ROWS, {"Size": "Double - Pack of 4"}), "Double Pack of 4")

    def test_pack_from_title(self):
        self.assertEqual(
            pick(PACK_ROWS, {"Size": "Single"}, title="Fitted Sheet Single Pack of 6 Grey"),
            "Single Pack of 6"
        )

    def test_pack_from_package_quantity(self):
        self.assertEqual(pick(PACK_ROWS, {"Size": "Double", "Item Package Quantity": "2"}), "Double Pack of 2")

    def test_number_of_items_confirms_pack(self):
        self.assertEqual(pick(PACK_ROWS, {"Size": "Single", "Number of Items": "4"}), "Single Pack of 4")

    def test_plain_row_used_when_no_pack_shown(self):
        self.assertEqual(pick(PACK_ROWS, {"Size": "Double"}), "Double")

    def test_title_size_words_are_ignored(self):
        # The title mentions King, but Amazon's size is Double.
        self.assertEqual(pick(PACK_ROWS, {"Size": "Double"}, title="Fits Double and King beds"), "Double")


class FullCheckTests(unittest.TestCase):

    def test_report_names_row_and_what_amazon_shows(self):
        spec = {"set_name": "Duvets", "product_type": "Duvet Cover Set", "rows": DUVET_ROWS}
        report = check_against_spec(
            {"Size": "Super King", "Number of Pieces": "4", "Item Weight": "1 Kilograms"}, spec
        )
        self.assertEqual(report["status"], STATUS_CHECKED)
        self.assertEqual(report["template_size"], "SKing 4 Piece")
        self.assertIn("Superking", report["variant_read"])
        self.assertIn("4 pieces", report["variant_read"])

    def test_no_row_reports_size_not_in_template(self):
        spec = {"set_name": "Duvets", "product_type": "Duvet Cover Set", "rows": DUVET_ROWS}
        report = check_against_spec({"Size": "Double", "Number of Pieces": "6"}, spec)
        self.assertEqual(report["status"], STATUS_NO_SIZE)


class SingleSetIsNotAPackTests(unittest.TestCase):
    """Live case: a Single set (1 duvet + 1 pillowcase) was matched to Single Pack of 2."""

    ROWS = rows("Single", "Single Pack of 2", "Double", "Double Pack of 2")

    PAGE = {"Size": "Single", "Number of Pieces": "2", "Number of Items": "2",
            "Number of Packs": "1",
            "Included Components": "Duvet Cover Set (1 x Duvet Cover + 2 x Pillowcase)"}

    def test_single_set_picks_single_row(self):
        self.assertEqual(pick(self.ROWS, self.PAGE), "Single")

    def test_items_equal_to_pieces_is_not_a_pack(self):
        page = dict(self.PAGE)
        page.pop("Number of Packs")
        self.assertEqual(pick(self.ROWS, page), "Single")

    def test_real_pack_of_2_still_found(self):
        page = {"Size": "Single - Pack of 2", "Number of Pieces": "4", "Number of Packs": "2"}
        self.assertEqual(pick(self.ROWS, page), "Single Pack of 2")

    def test_number_of_packs_2(self):
        self.assertEqual(pick(self.ROWS, {"Size": "Double", "Number of Packs": "2"}), "Double Pack of 2")


class SpellingTests(unittest.TestCase):

    def test_microfibre_is_a_check_not_a_mismatch(self):
        from modules.spec_checker import compare_value, RESULT_CHECK
        result, _ = compare_value("100% Premium Microfiber", "100% Premium Microfibre")
        self.assertEqual(result, RESULT_CHECK)

    def test_different_words_still_mismatch(self):
        from modules.spec_checker import compare_value, RESULT_MISMATCH
        self.assertEqual(compare_value("Satin", "Embossed Stripe")[0], RESULT_MISMATCH)


if __name__ == "__main__":
    unittest.main()
