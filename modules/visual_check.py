"""
Colour and video consistency (free, offline, no AI).

1. COLOUR NAME vs LISTING IMAGES
   The page's colour (e.g. "Blue", "Bricks - Navy Blue", "Taupe") is
   compared with the first listing images: is that colour really
   visible on the product? Example of a problem: the "Blue" ASIN shows
   grey bedding. Design names without a colour word (e.g. "Bricks")
   are not judged. White products are not judged (white = background).

2. VIDEOS vs LISTING IMAGES
   The thumbnails of the videos shown with the listing images are
   compared with the listing images, the same way as A+ images: a video
   of another design is flagged.

Both are strong HINTS, not proof: they are reported as "Check" (look
by eye), never as a confirmed error.
"""

import colorsys
import re
from io import BytesIO

from PIL import Image

from modules.design_match import (
    colour_signature,
    download_images,
    similarity,
    verdict_for,
    VERDICT_DIFFERENT,
    VERDICT_UNCERTAIN,
)


# How many listing images are looked at for the colour (main + 2).
COLOUR_IMAGES = 3

# The named colour must cover at least this share of the product pixels
# (white background removed) in at least one of those images.
MIN_COLOUR_SHARE = 0.08

MAX_VIDEOS = 6


def _is(name):
    """Build a test for one colour family: f(hue 0-360, sat 0-1, val 0-1)."""

    tests = {
        "red":    lambda h, s, v: (h < 15 or h >= 345) and s > 0.35 and v > 0.2,
        "orange": lambda h, s, v: 15 <= h < 40 and s > 0.45 and v > 0.4,
        "yellow": lambda h, s, v: 40 <= h < 68 and s > 0.3 and v > 0.4,
        "green":  lambda h, s, v: 68 <= h < 165 and s > 0.12 and v > 0.15,
        "teal":   lambda h, s, v: 165 <= h < 200 and s > 0.18 and v > 0.15,
        "blue":   lambda h, s, v: 195 <= h < 255 and s > 0.18 and v > 0.1,
        "purple": lambda h, s, v: 255 <= h < 300 and s > 0.12 and v > 0.12,
        "pink":   lambda h, s, v: (300 <= h < 345 and s > 0.12) or
                                  ((h < 20 or h >= 340) and 0.1 < s <= 0.35 and v > 0.6),
        "brown":  lambda h, s, v: 10 <= h < 50 and 0.12 < s < 0.75 and 0.15 < v < 0.95,
        "taupe":  lambda h, s, v: (h < 60 or h >= 330) and 0.04 < s < 0.3 and 0.25 < v < 0.85,
        "grey":   lambda h, s, v: s < 0.14 and 0.15 < v < 0.88,
        "black":  lambda h, s, v: v < 0.18,
    }

    return tests[name]


# Colour words in names -> colour family.
COLOUR_WORDS = {
    "red": "red", "burgundy": "red", "wine": "red", "maroon": "red", "crimson": "red",
    "terracotta": "orange", "orange": "orange", "rust": "orange", "coral": "orange",
    "peach": "orange", "apricot": "orange",
    "yellow": "yellow", "mustard": "yellow", "ochre": "yellow", "gold": "yellow", "lemon": "yellow",
    "green": "green", "sage": "green", "olive": "green", "mint": "green", "emerald": "green",
    "forest": "green", "khaki": "green",
    "teal": "teal", "turquoise": "teal", "aqua": "teal", "duck": "teal", "petrol": "teal",
    "blue": "blue", "navy": "blue", "denim": "blue", "royal": "blue", "sky": "blue",
    "indigo": "blue", "cobalt": "blue",
    "purple": "purple", "lilac": "purple", "lavender": "purple", "plum": "purple",
    "mauve": "purple", "violet": "purple", "aubergine": "purple", "heather": "purple",
    "pink": "pink", "blush": "pink", "rose": "pink", "fuchsia": "pink", "dusky": "pink",
    "brown": "brown", "chocolate": "brown", "mocha": "brown", "coffee": "brown",
    "camel": "brown", "tan": "brown", "caramel": "brown", "beige": "brown", "natural": "brown",
    "sand": "brown", "oatmeal": "brown", "latte": "brown", "biscuit": "brown",
    "taupe": "taupe", "mink": "taupe", "stone": "taupe", "linen": "taupe",
    "grey": "grey", "gray": "grey", "silver": "grey", "charcoal": "grey", "slate": "grey",
    "dove": "grey", "graphite": "grey", "smoke": "grey",
    "black": "black", "jet": "black",
}


def colour_families(colour_name):
    """Colour families named in a colour/design name, e.g. 'Bricks - Navy' -> {'blue'}."""

    words = re.findall(r"[a-z]+", str(colour_name or "").lower())

    return {COLOUR_WORDS[word] for word in words if word in COLOUR_WORDS}


def colour_share(image_bytes, family):
    """
    Share (0-1) of the product pixels in one colour family.
    Near-white pixels (background) are ignored.
    """

    image = Image.open(BytesIO(image_bytes))
    image.draft("RGB", (128, 128))
    image = image.convert("RGB").resize((64, 64))

    test = _is(family)

    counted = matched = 0

    for red, green, blue in zip(*[iter(image.tobytes())] * 3):

        h, s, v = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)

        if v > 0.92 and s < 0.08:
            continue  # white background

        counted += 1

        if test(h * 360, s, v):
            matched += 1

    return matched / counted if counted else 0.0


def check_colour(colour_name, image_list):
    """
    image_list: [(label, bytes)] of the first listing images.
    Returns (report, findings).
    """

    families = colour_families(colour_name)

    report = {"colour": colour_name or "", "families": sorted(families), "shares": [], "status": ""}

    if not colour_name:
        report["status"] = "NO COLOUR NAME ON THE PAGE"
        return report, []

    if not families:
        report["status"] = "NAME HAS NO COLOUR WORD - NOT JUDGED"
        return report, []

    best = 0.0

    for label, data in image_list[:COLOUR_IMAGES]:

        if not data:
            continue

        try:
            share = max(colour_share(data, family) for family in families)
        except Exception:
            continue

        report["shares"].append({"Image": label, "Colour share": round(share, 2)})

        best = max(best, share)

    if not report["shares"]:
        report["status"] = "IMAGES NOT READ"
        return report, []

    if best >= MIN_COLOUR_SHARE:
        report["status"] = "COLOUR VISIBLE"
        return report, []

    report["status"] = "COLOUR NOT SEEN - REVIEW"

    return report, [{
        "area": "Colour check",
        "rule": f"Listing images may not show the colour '{colour_name}'",
        "found": f"{round(best * 100)}% of the product in that colour",
        "expected": f"The {', '.join(sorted(families))} product",
        "severity": "Check",
        "action": "Look at the main images: if they show another colour, replace them.",
    }]


# Video thumbnails next to the listing images. The size part of the
# link (e.g. "._SX38_SY50_CR,0,0,38,50_") is removed to get the full frame.
VIDEO_JS = """
() => {
    const urls = [];
    const selector = [
        '#altImages li.videoThumbnail img', '#altImages .videoBlockIngress img',
        '#altImages [class*="video"] img', '#imageBlock [class*="video"] img',
        '#imageBlockVideoThumbnails img', '[data-csa-c-type="video"] img'
    ].join(',');
    document.querySelectorAll(selector).forEach(img => {
        let url = img.getAttribute('src') || '';
        if (!url.startsWith('https://') || url.includes('play-icon') || url.includes('transparent-pixel')) return;
        url = url.replace(/\\._[^/]*_\\./, '.');
        if (!urls.includes(url)) urls.push(url);
    });
    return urls;
}
"""


def read_video_thumbnails(page):
    """Links of the video thumbnails shown with the listing images."""

    try:
        return list(page.evaluate(VIDEO_JS) or [])[:MAX_VIDEOS]
    except Exception:
        return []


def compare_videos(video_signatures, listing_signatures):
    """
    video_signatures: [(url, signature or None)].
    Returns (rows, findings).
    """

    rows = []
    findings = []

    for number, (url, signature) in enumerate(video_signatures, start=1):

        if signature is None or not listing_signatures:
            rows.append({"Video": number, "URL": url, "Score": None, "Verdict": "NOT CHECKED"})
            continue

        score = max(similarity(signature, other) for _, other in listing_signatures)

        verdict = verdict_for(score)

        rows.append({"Video": number, "URL": url, "Score": round(score, 2), "Verdict": verdict})

        if verdict in (VERDICT_DIFFERENT, VERDICT_UNCERTAIN):
            findings.append({
                "area": f"Video {number}",
                "rule": "Video may show a different design",
                "found": f"Colour match {round(score * 100)}%",
                "expected": "Same design as the listing images",
                "severity": "Check",
                "action": "Play the video: if it shows another design, replace it.",
            })

    return rows, findings


def check_visual(page, content, display_report, images):
    """
    Colour name + video checks for one product.
    images: {url: bytes} already downloaded (listing and A+ images).
    Returns {"colour": {...}, "videos": [...], "findings": [...]}.
    """

    content = content or {}
    details = content.get("technical_details") or {}
    selections = content.get("variations") or {}

    colour_name = (
        selections.get("color_name") or selections.get("colour_name")
        or details.get("Colour") or details.get("Color") or ""
    )

    listing_urls = ((display_report or {}).get("listing_images") or {}).get("images", [])

    image_list = [(f"Listing image {n}", images.get(url)) for n, url in enumerate(listing_urls, start=1)]

    colour_report, findings = check_colour(colour_name, image_list)

    video_urls = read_video_thumbnails(page)

    video_rows = []

    if video_urls:

        video_images = download_images(page, video_urls)

        listing_signatures = []

        for url in listing_urls:
            try:
                if images.get(url):
                    listing_signatures.append((url, colour_signature(images[url])))
            except ValueError:
                pass

        video_signatures = []

        for url in video_urls:
            try:
                data = video_images.get(url)
                video_signatures.append((url, colour_signature(data) if data else None))
            except ValueError:
                video_signatures.append((url, None))

        video_rows, video_findings = compare_videos(video_signatures, listing_signatures)

        findings += video_findings

    return {"colour": colour_report, "videos": video_rows, "findings": findings}
