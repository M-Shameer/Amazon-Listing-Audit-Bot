"""
Tests for the A+ / Brand Story / images check and the A+ design match.

No browser and no Amazon: pages are fake and the "designs" are simple
pictures drawn with Pillow (grey with gold stripes vs brick red).

Run from the project folder:
    python -m unittest discover -s tests -t . -v
"""

import unittest
from io import BytesIO

from PIL import Image, ImageDraw

from modules.content_display import (
    summarise_display,
    is_content_image,
    unique_images,
    image_key,
    STATUS_DISPLAYED,
    STATUS_NOT_DISPLAYED,
    STATUS_NOT_VERIFIED,
)
from modules.design_match import (
    colour_signature,
    similarity,
    compare_signatures,
    check_aplus_design,
    analyse_image,
    skip_reason,
    VERDICT_SKIPPED,
    VERDICT_SAME,
    VERDICT_DIFFERENT,
    VERDICT_NOT_CHECKED,
)
from services.audit_service import content_findings


# Real URL shapes used by Amazon UK.
MAIN = "https://m.media-amazon.com/images/I/71abcDEF12L._AC_SL1500_.jpg"
MAIN_SMALL = "https://m.media-amazon.com/images/I/71abcDEF12L._AC_US40_.jpg"
GALLERY = "https://m.media-amazon.com/images/I/81xyzXYZ34L._AC_US40_.jpg"
APLUS = "https://m.media-amazon.com/images/S/aplus-media-library-service-media/1a2b3c.__CR0,0,970,600_PT0_SX970_V1___.jpg"
PIXEL = "https://m.media-amazon.com/images/G/02/x-locale/common/grey-pixel.gif"


def picture(background, stripe, room=None):
    """Draw a simple striped 'duvet' picture, optionally in a 'room'."""

    image = Image.new("RGB", (300, 300), background)
    draw = ImageDraw.Draw(image)

    for x in range(0, 300, 30):
        draw.rectangle([x, 0, x + 12, 300], fill=stripe)

    if room:
        draw.rectangle([0, 0, 300, 120], fill=room)

    buffer = BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


def text_panel():
    """A mostly white A+ panel with a little dark text, like a feature chart."""

    image = Image.new("RGB", (970, 300), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 40, 300, 70], fill=(30, 30, 30))
    draw.rectangle([40, 100, 260, 120], fill=(80, 80, 80))
    buffer = BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


TEXT_PANEL = text_panel()

GREY_GOLD = picture((128, 128, 130), (200, 160, 40))
GREY_GOLD_ROOM = picture((128, 128, 130), (200, 160, 40), room=(235, 230, 220))
BRICKS_ROOM = picture((170, 70, 50), (230, 220, 210), room=(235, 230, 220))


class ContentDisplayTests(unittest.TestCase):

    def test_image_filter(self):
        self.assertTrue(is_content_image(MAIN))
        self.assertTrue(is_content_image(APLUS))
        self.assertFalse(is_content_image(APLUS, allow_aplus_media=False))
        self.assertFalse(is_content_image(PIXEL))

    def test_displayed_sections(self):
        raw = {
            "aplus": {"found": True, "images": [APLUS, APLUS, PIXEL], "modules": 4,
                      "text_length": 500, "selector": "#aplus_feature_div"},
            "brand_story": {"found": True, "images": [APLUS], "modules": 0,
                            "text_length": 80, "selector": "#aplusBrandStory_feature_div"},
        }

        report = summarise_display(raw, [MAIN, MAIN_SMALL, GALLERY, PIXEL], page_ok=True)

        # The same image in two sizes counts once; pixels are ignored.
        self.assertEqual(report["listing_images"]["count"], 2)
        self.assertEqual(report["aplus"]["status"], STATUS_DISPLAYED)
        self.assertEqual(report["aplus"]["image_count"], 1)
        self.assertEqual(report["brand_story"]["status"], STATUS_DISPLAYED)

    def test_missing_aplus(self):
        report = summarise_display({"aplus": {"found": False}, "brand_story": {}}, [MAIN], True)
        self.assertEqual(report["aplus"]["status"], STATUS_NOT_DISPLAYED)

    def test_page_not_read_is_not_verified(self):
        report = summarise_display({}, [], page_ok=False)
        self.assertEqual(report["aplus"]["status"], STATUS_NOT_VERIFIED)
        self.assertEqual(report["listing_images"]["status"], STATUS_NOT_VERIFIED)


class ImageFilterTests(unittest.TestCase):

    APLUS_BIG = APLUS
    APLUS_SMALL_SIZE = APLUS.replace("SX970", "SX300")

    def test_same_image_in_two_sizes_counts_once(self):
        self.assertEqual(image_key(self.APLUS_BIG), image_key(self.APLUS_SMALL_SIZE))
        self.assertEqual(len(unique_images([self.APLUS_BIG, self.APLUS_SMALL_SIZE])), 1)

    def test_hidden_phone_copy_is_dropped(self):
        phone = APLUS.replace("1a2b3c", "9z8y7x")
        entries = [
            {"url": APLUS, "w": 970, "h": 600, "visible": True},
            {"url": phone, "w": 0, "h": 0, "visible": False},
        ]
        self.assertEqual(unique_images(entries), [APLUS])

    def test_icon_sized_image_is_dropped(self):
        icon = APLUS.replace("1a2b3c", "icon01")
        entries = [
            {"url": APLUS, "w": 970, "h": 600, "visible": True},
            {"url": icon, "w": 60, "h": 60, "visible": True},
        ]
        self.assertEqual(unique_images(entries), [APLUS])

    def test_text_panel_is_skipped_not_flagged(self):
        signature, info = analyse_image(TEXT_PANEL)
        self.assertTrue(skip_reason(info))

        listing = [(MAIN, colour_signature(GREY_GOLD))]
        rows, overall = compare_signatures(
            [("photo", colour_signature(GREY_GOLD_ROOM), ""),
             ("panel", signature, skip_reason(info))],
            listing
        )

        self.assertEqual(rows[1]["Verdict"], VERDICT_SKIPPED)
        self.assertEqual(overall, VERDICT_SAME)   # the panel does not cause a warning

    def test_room_photo_is_not_skipped(self):
        self.assertEqual(skip_reason(analyse_image(GREY_GOLD_ROOM)[1]), "")


class DesignMatchTests(unittest.TestCase):

    def test_same_design_scores_higher_than_other_design(self):
        same = similarity(colour_signature(GREY_GOLD), colour_signature(GREY_GOLD_ROOM))
        other = similarity(colour_signature(GREY_GOLD), colour_signature(BRICKS_ROOM))
        self.assertGreater(same, other)

    def test_verdicts(self):
        listing = [(MAIN, colour_signature(GREY_GOLD))]

        rows, overall = compare_signatures(
            [("same", colour_signature(GREY_GOLD_ROOM))], listing
        )
        self.assertEqual(rows[0]["Verdict"], VERDICT_SAME)
        self.assertEqual(overall, VERDICT_SAME)

        rows, overall = compare_signatures(
            [("same", colour_signature(GREY_GOLD_ROOM)),
             ("other", colour_signature(BRICKS_ROOM))], listing
        )
        self.assertEqual(rows[1]["Verdict"], VERDICT_DIFFERENT)
        self.assertEqual(overall, VERDICT_DIFFERENT)

    def test_unreadable_image(self):
        with self.assertRaises(ValueError):
            colour_signature(b"not an image")

    def test_check_with_fake_downloads(self):

        class Response:
            def __init__(self, body):
                self.ok = body is not None
                self._body = body

            def body(self):
                return self._body

        class Request:
            files = {MAIN: GREY_GOLD, APLUS: BRICKS_ROOM}

            def get(self, url, timeout=None):
                return Response(self.files.get(url))

        class Page:
            request = Request()

        display = {"listing_images": {"images": [MAIN]}, "aplus": {"images": [APLUS]}}

        report = check_aplus_design(Page(), display)

        self.assertEqual(report["overall"], VERDICT_DIFFERENT)
        self.assertEqual(report["listing_images_used"], 1)

    def test_no_aplus_images(self):
        report = check_aplus_design(object(), {"aplus": {"images": []}})
        self.assertEqual(report["overall"], VERDICT_NOT_CHECKED)


class ContentFindingTests(unittest.TestCase):

    def test_findings(self):
        display = {
            "listing_images": {"status": STATUS_DISPLAYED},
            "aplus": {"status": STATUS_NOT_DISPLAYED},
            "brand_story": {"status": STATUS_DISPLAYED},
        }

        findings = content_findings(display, {"overall": VERDICT_DIFFERENT})

        items = [finding["Item"] for finding in findings]
        self.assertEqual(items, ["A+ content (EBC)", "A+ design match"])

    def test_no_findings_when_all_good(self):
        display = {key: {"status": STATUS_DISPLAYED} for key in ("listing_images", "aplus", "brand_story")}
        self.assertEqual(content_findings(display, {"overall": VERDICT_SAME}), [])


if __name__ == "__main__":
    unittest.main()
