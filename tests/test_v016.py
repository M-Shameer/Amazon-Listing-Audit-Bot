"""
Tests for version 0.16: size text consistency, dimensions printed on
images, colour name vs images, videos vs listing images.
No browser or internet needed.
"""

import unittest
from io import BytesIO

from PIL import Image, ImageDraw

from modules.size_text import find_sizes, check_size_text, page_dimensions
from modules.image_text import dimension_findings, analyse
from modules.visual_check import colour_families, check_colour, compare_videos
from modules.design_match import colour_signature
from services.history_service import issue_kind
from services.issue_report import build_issue_rows
from tests.test_quality import make_result


def rules(findings):
    return [finding["rule"] for finding in findings]


def picture(colour, background="white"):
    image = Image.new("RGB", (300, 300), background)
    ImageDraw.Draw(image).rectangle([50, 50, 250, 250], fill=colour)
    buffer = BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


class SizeTextTests(unittest.TestCase):

    def test_same_size_different_spacing(self):
        content = {
            "title": "Duvet Cover Set King (220 x 230cm) Blue",
            "technical_details": {"Size": "King (220 x 230 cm) - Pack of 4"},
            "size_options": ["King (220 x 230 cm)"],
        }
        findings = check_size_text(content)
        self.assertEqual(rules(findings), ["Same size written differently"])
        self.assertIn("Title", findings[0]["found"])
        self.assertIn("220 x 230cm", findings[0]["found"])
        self.assertEqual(findings[0]["severity"], "Medium")

    def test_consistent_page_has_no_findings(self):
        content = {
            "title": "Duvet Cover Set King (220 x 230 cm)",
            "technical_details": {"Size": "King (220 x 230 cm)"},
            "size_options": ["Double (200 x 200 cm)", "King (220 x 230 cm)", "Super King (260 x 220 cm)"],
        }
        self.assertEqual(check_size_text(content), [])

    def test_variations_in_different_styles(self):
        content = {"size_options": ["Double (200 x 200cm)", "King (220 x 230 cm)"]}
        findings = check_size_text(content)
        self.assertEqual(rules(findings), ["Sizes not written in the same style"])
        self.assertEqual(findings[0]["severity"], "Low")

    def test_super_king_is_one_size(self):
        self.assertEqual(find_sizes("Super King (260 x 220 cm)")[0]["key"], ("Super King", 260.0, 220.0))
        self.assertEqual(find_sizes("SKing 260 x 220 cm")[0]["key"], ("Super King", 260.0, 220.0))

    def test_pillowcase_sizes_are_not_bed_sizes(self):
        self.assertEqual(find_sizes("2 pillowcases 50 x 75 cm"), [])

    def test_page_dimensions(self):
        content = {"technical_details": {"Size": "King (220 x 230 cm) - Pack of 4"}}
        self.assertEqual(page_dimensions(content), [(220.0, 230.0)])


class ImageDimensionTests(unittest.TestCase):

    PAGE = [(220.0, 230.0)]

    def test_wrong_size_on_image(self):
        findings = dimension_findings("DUVET 200 X 200 CM", "Listing image 3", self.PAGE)
        self.assertEqual(rules(findings), ["Image text: different dimensions"])
        self.assertEqual(findings[0]["found"], "200 x 200 cm")

    def test_right_size_any_order_or_inches(self):
        self.assertEqual(dimension_findings("230 x 220 cm", "x", self.PAGE), [])
        self.assertEqual(dimension_findings('86.6 x 90.6"', "x", self.PAGE), [])

    def test_pillowcase_only_is_ignored(self):
        self.assertEqual(dimension_findings("PILLOWCASE 50 x 75 cm", "x", self.PAGE), [])

    def test_size_chart_is_ignored(self):
        chart = "SINGLE 135 x 200 cm DOUBLE 200 x 200 cm KING 220 x 230 cm"
        self.assertEqual(dimension_findings(chart, "x", self.PAGE), [])

    def test_only_listing_images(self):
        rows = [{"kind": "A+ image", "number": 1, "url": "u", "text": "200 x 200 cm"}]
        self.assertEqual(analyse(rows, set(), self.PAGE), [])


class ColourTests(unittest.TestCase):

    def test_colour_words(self):
        self.assertEqual(colour_families("Bricks - Navy Blue"), {"blue"})
        self.assertEqual(colour_families("Bricks"), set())
        self.assertEqual(colour_families("Taupe"), {"taupe"})

    def test_blue_listing_with_grey_images_is_flagged(self):
        report, findings = check_colour("Bricks Blue", [("Listing image 1", picture((128, 128, 130)))])
        self.assertEqual(report["status"], "COLOUR NOT SEEN - REVIEW")
        self.assertEqual(findings[0]["severity"], "Check")

    def test_blue_listing_with_blue_images_passes(self):
        report, findings = check_colour("Navy", [("Listing image 1", picture((25, 40, 90)))])
        self.assertEqual(report["status"], "COLOUR VISIBLE")
        self.assertEqual(findings, [])

    def test_design_name_only_is_not_judged(self):
        report, findings = check_colour("Bricks", [("Listing image 1", picture((128, 128, 130)))])
        self.assertEqual(findings, [])


class VideoTests(unittest.TestCase):

    def test_video_of_another_design_is_flagged(self):
        # Full-frame pictures, like real video frames (no white page).
        navy_room = picture((25, 40, 90), background=(60, 70, 110))
        gold_room = picture((200, 160, 40), background=(150, 120, 60))
        listing = [("l1", colour_signature(navy_room))]
        videos = [("v1", colour_signature(navy_room)),
                  ("v2", colour_signature(gold_room))]
        rows, findings = compare_videos(videos, listing)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rules(findings), ["Video may show a different design"])
        self.assertEqual(findings[0]["area"], "Video 2")

    def test_findings_reach_issues_and_tracking(self):
        result = make_result("B000000001")
        result["visual"] = {"findings": [{
            "area": "Video 2", "rule": "Video may show a different design", "found": "",
            "expected": "", "severity": "Check", "action": "x"}]}
        areas = {row["Area"] for row in build_issue_rows([result])}
        self.assertIn("Video 2", areas)
        self.assertEqual(issue_kind("Check | Video may show a different design", "Video 2"), "design")


if __name__ == "__main__":
    unittest.main()
