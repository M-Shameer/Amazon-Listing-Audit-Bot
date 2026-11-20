"""
Tests for grouping variations by base size in the Variation Matrix:
"King" covers every King pack / piece variation in every colour.
No browser or internet needed.
"""

import unittest

from services.variation_service import (
    base_size,
    base_size_options,
    variations_of_base,
    items_for_base_size,
    group_by_size,
)


ROWS = [
    {"asin": "B0AAAAAA01", "colour": "Taupe", "size": "King (220 x 230 cm) - Pack of 4"},
    {"asin": "B0AAAAAA02", "colour": "Blue", "size": "King (220 x 230 cm) - Pack of 4"},
    {"asin": "B0AAAAAA03", "colour": "Taupe", "size": "King 3 Piece"},
    {"asin": "B0AAAAAA04", "colour": "Taupe", "size": "SKing 4 Piece"},
    {"asin": "B0AAAAAA05", "colour": "Blue", "size": "Super King (260 x 220 cm)"},
    {"asin": "B0AAAAAA06", "colour": "Grey", "size": "Double"},
    {"asin": "B0AAAAAA07", "colour": "Grey", "size": "Single 2 Pack"},
]


class BaseSizeTests(unittest.TestCase):

    def test_base_size_names(self):
        self.assertEqual(base_size("King (220 x 230 cm) - Pack of 4"), "King")
        self.assertEqual(base_size("SKing 4 Piece"), "Super King")
        self.assertEqual(base_size("S King"), "Super King")
        self.assertEqual(base_size("Small Double 3 Piece"), "Small Double")
        self.assertEqual(base_size("200 x 200 cm"), "200 x 200 cm")

    def test_king_never_includes_super_king(self):
        self.assertEqual(variations_of_base(ROWS, "King"),
                         ["King (220 x 230 cm) - Pack of 4", "King 3 Piece"])

    def test_options_smallest_first_with_counts(self):
        self.assertEqual(base_size_options(ROWS),
                         [("Single", 1), ("Double", 1), ("King", 3), ("Super King", 2)])

    def test_all_packs_pieces_and_colours(self):
        items = items_for_base_size(ROWS, "King")
        self.assertEqual({item["asin"] for item in items}, {"B0AAAAAA01", "B0AAAAAA02", "B0AAAAAA03"})
        self.assertEqual(items[0]["url"], "https://www.amazon.co.uk/dp/B0AAAAAA01")

    def test_only_chosen_variations(self):
        items = items_for_base_size(ROWS, "King", ["King 3 Piece"])
        self.assertEqual([item["asin"] for item in items], ["B0AAAAAA03"])

    def test_colours_compared_within_the_same_variation(self):
        items = items_for_base_size(ROWS, "King")
        results = [{"asin": item["asin"]} for item in items]
        groups = group_by_size(results, items)
        self.assertEqual(len(groups["King (220 x 230 cm) - Pack of 4"]), 2)
        self.assertEqual(len(groups["King 3 Piece"]), 1)


if __name__ == "__main__":
    unittest.main()
