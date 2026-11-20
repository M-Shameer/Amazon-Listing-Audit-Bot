"""
Text inside images (OCR) - free, offline, on this laptop.

Uses RapidOCR (pip package "rapidocr" with "onnxruntime"). No account,
no API key, no internet service. The text models are downloaded once
by "Install Audit Bot.bat"; after that it works offline.

What it checks:
- Spelling in listing and A+ images (British English, e.g. Microfiber
  -> Microfibre, Color -> Colour).
- Listing images that name a DIFFERENT size, number of pieces or pack
  than the product page (e.g. the image says "4 PIECE" but the product
  is a 3-piece set). Images that name several sizes (size charts) are
  not judged.
- Listing images that print bed DIMENSIONS different from the product's
  size (e.g. the image says "200 x 200 cm" on a King 220 x 230 cm
  listing). Pillowcase sizes (under 90 cm) and size charts (several bed
  sizes on one image) are not judged. Order and inches are handled. A+ images are only spell-checked, because A+ modules
  often show the whole range on purpose.

SPEED: reading text takes about a second per image, so it runs in a
background thread while Chrome loads the next product. A batch only
waits for whatever is still unread at the very end.

If OCR is not installed, everything still works: the result simply
says "OCR not installed".
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from PIL import Image

from modules.spec_checker import variant_tokens
from modules.size_text import DIMENSION_PATTERN, to_cm


# How many images per product are read (most text sits in the first ones).
MAX_LISTING_IMAGES = 7
MAX_APLUS_IMAGES = 8

# Images are shrunk to this longest side before reading (faster, still sharp).
MAX_SIDE = 1100

# Lines read with lower confidence than this are ignored.
MIN_SCORE = 0.6

STATUS_READ = "READ"
STATUS_NOT_INSTALLED = "OCR NOT INSTALLED"
STATUS_NO_IMAGES = "NO IMAGES"
STATUS_FAILED = "FAILED"

# American spellings that should be British on Amazon UK.
UK_SPELLING = {
    "microfiber": "microfibre",
    "fiber": "fibre",
    "fibers": "fibres",
    "color": "colour",
    "colors": "colours",
    "gray": "grey",
    "center": "centre",
    "favorite": "favourite",
    "odor": "odour",
    "odorless": "odourless",
}

_ENGINE = None
_ENGINE_ERROR = ""

# One background worker: the OCR engine already uses several CPU cores.
_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="image-text")


# =========================================
# 1. THE OCR ENGINE
# =========================================

def _engine():
    """Load RapidOCR once. Returns the engine or None if not installed."""

    global _ENGINE, _ENGINE_ERROR

    if _ENGINE is not None or _ENGINE_ERROR:
        return _ENGINE

    try:
        from rapidocr import RapidOCR
        _ENGINE = RapidOCR()
    except Exception as error:
        _ENGINE_ERROR = str(error) or error.__class__.__name__

    return _ENGINE


def ocr_available():
    """(True, "") when OCR works, else (False, reason)."""

    engine = _engine()

    return (engine is not None, "" if engine is not None else _ENGINE_ERROR)


def warm_up():
    """
    Load the engine once (downloads the text models the first time).
    Used by the installer. Returns a short message.
    """

    ok, reason = ocr_available()

    if not ok:
        return "OCR not available: " + reason

    blank = Image.new("RGB", (200, 60), "white")

    read_text(_to_bytes(blank))

    return "OCR ready."


def _to_bytes(image):

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def read_text(image_bytes):
    """
    Read the text lines in one image.
    Returns [(text, score)] with low-confidence lines removed.
    """

    engine = _engine()

    if engine is None or not image_bytes:
        return []

    import numpy

    image = Image.open(BytesIO(image_bytes))
    image.draft("RGB", (MAX_SIDE, MAX_SIDE))
    image = image.convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))

    # RapidOCR expects BGR colour order (like OpenCV).
    array = numpy.array(image)[:, :, ::-1].copy()

    output = engine(array)

    texts = getattr(output, "txts", None) or ()
    scores = getattr(output, "scores", None) or ()

    return [
        (str(text).strip(), float(score))
        for text, score in zip(texts, scores)
        if str(text).strip() and float(score) >= MIN_SCORE
    ]


# =========================================
# 2. BACKGROUND READING
# =========================================

def choose_images(display_report):
    """
    The images to read: [(kind, number, url)].
    kind is "Listing image" or "A+ image".
    """

    display_report = display_report or {}

    listing = (display_report.get("listing_images") or {}).get("images", [])[:MAX_LISTING_IMAGES]
    aplus = (display_report.get("aplus") or {}).get("images", [])[:MAX_APLUS_IMAGES]

    chosen = [("Listing image", number, url) for number, url in enumerate(listing, start=1)]
    chosen += [("A+ image", number, url) for number, url in enumerate(aplus, start=1)]

    return chosen


def _read_all(chosen, images):
    """Runs in the background thread. Returns (status, rows, seconds)."""

    start = time.perf_counter()

    ok, reason = ocr_available()

    if not ok:
        return STATUS_NOT_INSTALLED, [], 0.0

    rows = []

    for kind, number, url in chosen:

        lines = []

        try:
            lines = read_text(images.get(url))
        except Exception:
            lines = []

        rows.append({
            "kind": kind,
            "number": number,
            "url": url,
            "text": " | ".join(text for text, _ in lines),
        })

    return STATUS_READ, rows, round(time.perf_counter() - start, 1)


def start_reading(display_report, images):
    """
    Start reading the text of this product's images in the background.
    images: {url: bytes} (already downloaded). Returns a Future.
    """

    chosen = choose_images(display_report)

    return _POOL.submit(_read_all, chosen, dict(images or {}))


# =========================================
# 3. CHECKS ON THE TEXT (pure functions, unit tested)
# =========================================

def spelling_findings(text, area):
    """American spellings in one image's text."""

    findings = []

    for word, british in UK_SPELLING.items():

        if re.search(r"\b" + word + r"\b", text, re.IGNORECASE):

            findings.append({
                "area": area,
                "rule": f"Image text: spelling '{word.capitalize()}'",
                "found": word.capitalize(),
                "expected": british.capitalize(),
                "severity": "Low",
                "action": "Correct the spelling on the image and upload it again.",
            })

    return findings


def _values(tokens, kind):
    return {token.split(":")[1] for token in tokens if token.startswith(kind + ":")}


def variation_findings(text, area, amazon_tokens):
    """
    A listing image that names a different size, piece count or pack
    than the product page. Only judged when the image names exactly one
    value, so size charts and "available in" images are not flagged.
    """

    findings = []

    image_tokens = variant_tokens(text)

    image_sizes = {token for token in image_tokens if ":" not in token}
    page_sizes = {token for token in amazon_tokens if ":" not in token}

    if len(image_sizes) == 1 and page_sizes and not image_sizes & page_sizes:

        findings.append({
            "area": area,
            "rule": "Image text: different size",
            "found": next(iter(image_sizes)).capitalize(),
            "expected": ", ".join(sorted(size.capitalize() for size in page_sizes)),
            # Size words have other meanings ("double stitched"), so a
            # person confirms this one.
            "severity": "Check",
            "action": "Look at the image: if it shows another size, replace it.",
        })

    page_items = _values(amazon_tokens, "items")

    for kind, label in (("pieces", "number of pieces"), ("pack", "pack")):

        image_values = _values(image_tokens, kind)

        # "Number of Items" may confirm pieces; a pack is only compared
        # when the page itself states a pack.
        page_values = _values(amazon_tokens, kind)
        if kind == "pieces":
            page_values |= page_items

        if len(image_values) == 1 and page_values and not image_values & page_values:

            findings.append({
                "area": area,
                "rule": f"Image text: different {label}",
                "found": next(iter(image_values)),
                "expected": ", ".join(sorted(page_values)),
                "severity": "Medium",
                "action": "Check the image shows the right set; replace it if not.",
            })

    return findings


# Bed dimensions are at least this long on both sides (pillowcases are smaller).
BED_MIN_CM = 90

# Two measurements this close (in cm) are the same size (rounding).
DIMENSION_TOLERANCE_CM = 3


def _same_dimensions(first, second):
    """True if two (a, b) pairs are the same size, in either order."""

    for a, b in (second, (second[1], second[0])):
        if abs(first[0] - a) <= DIMENSION_TOLERANCE_CM and abs(first[1] - b) <= DIMENSION_TOLERANCE_CM:
            return True

    return False


def dimension_findings(text, area, page_dims):
    """
    A listing image that prints ONE bed size that is not this product's
    size. page_dims: [(a, b)] in cm from the product page.
    """

    if not page_dims:
        return []

    pairs = []

    for match in DIMENSION_PATTERN.finditer(text or ""):
        pair = to_cm(match.group("a"), match.group("b"), match.group("unit"))
        if min(pair) >= BED_MIN_CM and not any(_same_dimensions(pair, seen) for seen in pairs):
            pairs.append(pair)

    # No bed size on the image, or a size chart with several sizes.
    if len(pairs) != 1:
        return []

    pair = pairs[0]

    if any(_same_dimensions(pair, page) for page in page_dims):
        return []

    def show(dimensions):
        return f"{dimensions[0]:g} x {dimensions[1]:g} cm"

    return [{
        "area": area,
        "rule": "Image text: different dimensions",
        "found": show(pair),
        "expected": " or ".join(show(page) for page in page_dims),
        "severity": "Medium",
        "action": "The image shows another size: replace it with this size's image.",
    }]


def analyse(rows, amazon_tokens, page_dims=()):
    """All findings for one product's image text."""

    findings = []

    for row in rows:

        text = row.get("text") or ""

        if not text:
            continue

        area = f"{row['kind']} {row['number']}"

        findings += spelling_findings(text, area)

        if row["kind"] == "Listing image":
            findings += variation_findings(text, area, amazon_tokens)
            findings += dimension_findings(text, area, list(page_dims or ()))

    return findings


def finish(result, amazon_tokens, timeout=180, page_dims=()):
    """
    Wait for the background reading of one product, then store
    result["image_text"] = {"status", "images", "findings", "seconds"}.
    Safe to call when no reading was started.
    """

    future = result.pop("_image_text_future", None)

    if future is None:
        return result

    try:
        status, rows, seconds = future.result(timeout=timeout)
    except Exception as error:
        result["image_text"] = {"status": STATUS_FAILED, "images": [], "findings": [],
                                "seconds": 0, "note": str(error)}
        return result

    if status == STATUS_READ and not rows:
        status = STATUS_NO_IMAGES

    result["image_text"] = {
        "status": status,
        "images": rows,
        "findings": analyse(rows, amazon_tokens, page_dims) if status == STATUS_READ else [],
        "seconds": seconds,
    }

    if seconds:
        result.setdefault("timings", {})["Image text (background)"] = seconds

    # A clean product with image-text problems now has issues.
    serious = [f for f in result["image_text"]["findings"] if f["severity"] in ("High", "Medium")]

    if serious and result.get("overall_status") == "NO RULE-BASED ISSUES FOUND":
        result["overall_status"] = "ISSUES FOUND"

    return result
