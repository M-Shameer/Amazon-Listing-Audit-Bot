"""
Tests for the text-inside-images checks. A fake OCR engine is used,
so these tests need neither RapidOCR nor internet.
"""

import unittest
from io import BytesIO

from PIL import Image

from modules import image_text
from modules.spec_checker import variant_tokens
from services.issue_report import build_issue_rows
from services.history_service import issue_kind
from tests.test_quality import make_result


def rules(findings):
    return [finding["rule"] for finding in findings]


class SpellingTests(unittest.TestCase):

    def test_american_spellings(self):
        findings = image_text.spelling_findings("SOFT MICROFIBER | 6 COLORS", "Listing image 2")
        self.assertIn("Image text: spelling 'Microfiber'", rules(findings))
        self.assertIn("Image text: spelling 'Colors'", rules(findings))
        self.assertTrue(all(f["area"] == "Listing image 2" for f in findings))

    def test_british_text_is_fine(self):
        self.assertEqual(image_text.spelling_findings("Soft microfibre in 6 colours", "x"), [])


class VariationTests(unittest.TestCase):

    def test_different_piece_count(self):
        page = {"double", "pieces:3"}
        findings = image_text.variation_findings("DOUBLE 4 PIECE SET", "Listing image 1", page)
        self.assertEqual(rules(findings), ["Image text: different number of pieces"])
        self.assertEqual(findings[0]["severity"], "Medium")

    def test_number_of_items_confirms_pieces(self):
        page = {"double", "items:4"}
        self.assertEqual(image_text.variation_findings("4 PIECE SET", "x", page), [])

    def test_different_size_is_check_by_eye(self):
        findings = image_text.variation_findings("KING SIZE", "x", {"double"})
        self.assertEqual(rules(findings), ["Image text: different size"])
        self.assertEqual(findings[0]["severity"], "Check")

    def test_size_chart_is_not_judged(self):
        self.assertEqual(
            image_text.variation_findings("SINGLE DOUBLE KING SUPER KING", "x", {"double"}), []
        )

    def test_pack_only_compared_when_page_states_a_pack(self):
        # "Set of 2 pillowcases" inside a 4-piece duvet set image.
        self.assertEqual(image_text.variation_findings("SET OF 2 PILLOWCASES", "x", {"double", "items:4"}), [])
        findings = image_text.variation_findings("PACK OF 4", "x", {"double", "pack:2"})
        self.assertEqual(rules(findings), ["Image text: different pack"])

    def test_aplus_images_only_spell_checked(self):
        rows = [{"kind": "A+ image", "number": 1, "url": "u", "text": "KING 6 PIECE"}]
        self.assertEqual(image_text.analyse(rows, {"double", "pieces:3"}), [])


class FakeOutput:
    def __init__(self, texts, scores):
        self.txts, self.scores = texts, scores


class FakeEngine:
    def __call__(self, array):
        return FakeOutput(("DOUBLE 4 PIECE", "MICROFIBER", "blurry"), (0.95, 0.9, 0.3))


def png_bytes():
    buffer = BytesIO()
    Image.new("RGB", (300, 200), "white").save(buffer, format="PNG")
    return buffer.getvalue()


class BackgroundReadingTests(unittest.TestCase):

    def setUp(self):
        self._engine, self._error = image_text._ENGINE, image_text._ENGINE_ERROR
        image_text._ENGINE, image_text._ENGINE_ERROR = FakeEngine(), ""

    def tearDown(self):
        image_text._ENGINE, image_text._ENGINE_ERROR = self._engine, self._error

    def test_read_text_drops_low_confidence(self):
        lines = image_text.read_text(png_bytes())
        self.assertEqual([text for text, _ in lines], ["DOUBLE 4 PIECE", "MICROFIBER"])

    def test_start_and_finish(self):
        display = {"listing_images": {"images": ["https://m.media-amazon.com/a.jpg"]},
                   "aplus": {"images": []}}
        result = make_result("B000000001", status="NO RULE-BASED ISSUES FOUND")
        result["timings"] = {}
        result["_image_text_future"] = image_text.start_reading(
            display, {"https://m.media-amazon.com/a.jpg": png_bytes()}
        )

        image_text.finish(result, variant_tokens("Double 3 Piece"))

        report = result["image_text"]
        self.assertEqual(report["status"], image_text.STATUS_READ)
        self.assertIn("Image text: different number of pieces", rules(report["findings"]))
        self.assertIn("Image text: spelling 'Microfiber'", rules(report["findings"]))
        self.assertEqual(result["overall_status"], "ISSUES FOUND")
        self.assertNotIn("_image_text_future", result)

        # The findings reach the Issues table and are tracked as OCR issues.
        areas = {row["Area"] for row in build_issue_rows([result])}
        self.assertIn("Listing image 1", areas)
        self.assertEqual(issue_kind("Medium | Image text: different number of pieces", "Listing image 1"), "ocr")

    def test_not_installed(self):
        image_text._ENGINE, image_text._ENGINE_ERROR = None, "No module named 'rapidocr'"
        result = make_result("B000000001")
        result["_image_text_future"] = image_text.start_reading(
            {"listing_images": {"images": ["u"]}}, {"u": png_bytes()}
        )
        image_text.finish(result, set())
        self.assertEqual(result["image_text"]["status"], image_text.STATUS_NOT_INSTALLED)


if __name__ == "__main__":
    unittest.main()
