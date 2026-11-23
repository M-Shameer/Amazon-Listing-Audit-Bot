"""
A+ design match check.

Question: do the A+ (EBC) images show the same design as the listing
images? Example of a problem: the "Bricks" ASIN shows A+ images of
the grey/gold design.

Method (free, offline, no AI):
1. Each image is shrunk to 64 x 64 pixels.
2. Its colours are counted into a "colour fingerprint": 24 colour
   groups (12 hues x pale/strong) plus 4 grey levels.
3. Each A+ image is compared with EVERY listing image and the best
   score is kept. Lifestyle A+ photos usually come from the same photo
   shoot as some gallery images, so the best match is the fair one.

Scores run from 0 (nothing in common) to 1 (identical colours).

IMPORTANT: this is a strong HINT, not proof. A+ photos include rooms
and backgrounds. Results marked POSSIBLE DIFFERENT DESIGN or UNCERTAIN
should be checked by eye; the website shows the pictures side by side.
Brand Story images are NOT compared, because a Brand Story normally
shows the whole brand range, not one design.
"""

import colorsys
import threading
from collections import OrderedDict
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from PIL import Image


# Score thresholds. Adjust after real audits if needed.
LIKELY_SAME = 0.50
POSSIBLY_DIFFERENT = 0.30

VERDICT_SAME = "LIKELY SAME DESIGN"
VERDICT_UNCERTAIN = "UNCERTAIN - REVIEW"
VERDICT_DIFFERENT = "POSSIBLE DIFFERENT DESIGN - REVIEW"
VERDICT_NOT_CHECKED = "NOT CHECKED"
VERDICT_SKIPPED = "SKIPPED - GRAPHIC OR TEXT"

# An image that is mostly plain white/very pale is a text panel, size
# chart or icon sheet, not a photo of the product, so it is skipped.
MAX_WHITE_FRACTION = 0.70
MIN_PHOTO_SIDE = 120

# Download safety limits.
MAX_IMAGE_BYTES = 5 * 1024 * 1024
DOWNLOAD_TIMEOUT_MS = 10000
MAX_APLUS_IMAGES = 12
MAX_LISTING_IMAGES = 10

# Images are downloaded this many at a time (much faster than one by one).
PARALLEL_DOWNLOADS = 8

HUE_BINS = 12
BIN_COUNT = HUE_BINS * 2 + 4


def analyse_image(image_bytes):
    """
    Return (signature, info) for an image.
    info: {"width", "height", "white_fraction"}.
    Raises ValueError for unreadable images.
    """

    try:
        image = Image.open(BytesIO(image_bytes))
        width, height = image.size
        # JPEG only: decode at a small size directly (much faster).
        image.draft("RGB", (256, 256))
        image = image.convert("RGB")
    except Exception as error:
        raise ValueError("Not a readable image: " + str(error))

    signature, white_fraction = _signature_of(image)

    return signature, {
        "width": width,
        "height": height,
        "white_fraction": round(white_fraction, 3)
    }


def skip_reason(info):
    """Why an image is not a product photo, or "" if it is one."""

    if min(info.get("width", 0), info.get("height", 0)) < MIN_PHOTO_SIDE:
        return "Too small (icon or logo)."

    if info.get("white_fraction", 0) > MAX_WHITE_FRACTION:
        return "Mostly plain white (text panel, chart or icons)."

    return ""


def colour_signature(image_bytes):
    """
    Return the colour fingerprint of an image: a list of BIN_COUNT
    numbers that add up to 1. Raises ValueError for unreadable images.
    """

    return analyse_image(image_bytes)[0]


def _signature_of(image):
    """Colour fingerprint and share of near-white pixels of a PIL image."""

    image = image.resize((64, 64))

    bins = [0.0] * BIN_COUNT

    white = 0

    # Raw bytes: R, G, B, R, G, B ... (works in old and new Pillow).
    pixels = image.tobytes()

    for start in range(0, len(pixels), 3):

        red, green, blue = pixels[start], pixels[start + 1], pixels[start + 2]

        hue, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)

        if value > 0.92 and saturation < 0.08:
            white += 1

        if saturation < 0.18 or value < 0.12:

            # Greys, black and white: 4 brightness levels.
            level = min(int(value * 4), 3)
            bins[HUE_BINS * 2 + level] += 1

        else:

            hue_bin = min(int(hue * HUE_BINS), HUE_BINS - 1)
            strength = 1 if saturation >= 0.5 else 0
            bins[hue_bin * 2 + strength] += 1

    total = sum(bins) or 1.0

    return [count / total for count in bins], white / total


def similarity(first, second):
    """Histogram intersection: 1.0 = same colours, 0.0 = nothing shared."""

    return round(sum(min(a, b) for a, b in zip(first, second)), 3)


def verdict_for(score):
    """Turn a score into a verdict."""

    if score is None:
        return VERDICT_NOT_CHECKED

    if score >= LIKELY_SAME:
        return VERDICT_SAME

    if score < POSSIBLY_DIFFERENT:
        return VERDICT_DIFFERENT

    return VERDICT_UNCERTAIN


def compare_signatures(aplus_signatures, listing_signatures):
    """
    Pure comparison (unit tested).

    aplus_signatures:   [(url, signature or None)] or
                        [(url, signature or None, skip_reason)]
    listing_signatures: [(url, signature)]

    Images with a skip reason (graphics, text panels, icons) are listed
    but not compared and do not affect the overall verdict.

    Returns (rows, overall_verdict).
    """

    rows = []

    for index, entry in enumerate(aplus_signatures, start=1):

        url, signature = entry[0], entry[1]
        reason = entry[2] if len(entry) > 2 else ""

        best_score = None
        best_url = ""

        if reason:

            rows.append({
                "A+ Image": index,
                "A+ Image URL": url,
                "Best Matching Listing Image": "",
                "Score": None,
                "Verdict": VERDICT_SKIPPED,
                "Note": reason
            })
            continue

        if signature is not None:
            for listing_url, listing_signature in listing_signatures:
                score = similarity(signature, listing_signature)
                if best_score is None or score > best_score:
                    best_score, best_url = score, listing_url

        rows.append({
            "A+ Image": index,
            "A+ Image URL": url,
            "Best Matching Listing Image": best_url,
            "Score": best_score,
            "Verdict": verdict_for(best_score),
            "Note": "" if signature is not None else "Could not be downloaded."
        })

    checked = [row for row in rows if row["Score"] is not None]

    if not checked:
        overall = VERDICT_NOT_CHECKED
    elif any(row["Verdict"] == VERDICT_DIFFERENT for row in checked):
        overall = VERDICT_DIFFERENT
    elif all(row["Verdict"] == VERDICT_SAME for row in checked):
        overall = VERDICT_SAME
    else:
        overall = VERDICT_UNCERTAIN

    return rows, overall


def download_image(page, url):
    """
    Download one image through the bot's own browser session.
    Returns bytes, or None if it fails or is too large.
    """

    try:
        response = page.request.get(url, timeout=DOWNLOAD_TIMEOUT_MS)

        if not response.ok:
            return None

        body = response.body()

        return body if len(body) <= MAX_IMAGE_BYTES else None

    except Exception:
        return None


# Images already downloaded in this session (a parent's listings share
# their A+ and many images, so each is downloaded only once).
_CACHE = OrderedDict()
_CACHE_LOCK = threading.Lock()
CACHE_MAX_BYTES = 250 * 1024 * 1024
_cache_bytes = [0]


def _cached(url):
    with _CACHE_LOCK:
        if url in _CACHE:
            _CACHE.move_to_end(url)
            return _CACHE[url]
    return None


def _remember(url, data):
    if not data:
        return
    with _CACHE_LOCK:
        if url in _CACHE:
            return
        _CACHE[url] = data
        _cache_bytes[0] += len(data)
        while _cache_bytes[0] > CACHE_MAX_BYTES and _CACHE:
            _, old = _CACHE.popitem(last=False)
            _cache_bytes[0] -= len(old)


def _fetch_public(url):
    """
    Download one public Amazon image (m.media-amazon.com) without the
    browser. Safe to run in a background thread. Returns bytes or None.
    """

    if not url.startswith("https://"):
        return None

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_MS / 1000) as response:
            body = response.read(MAX_IMAGE_BYTES + 1)

        return body if len(body) <= MAX_IMAGE_BYTES else None

    except Exception:
        return None


def download_images(page, urls):
    """
    Download many images at once. Returns {url: bytes or None}.
    Images that fail in parallel are retried through the browser.
    """

    unique = list(dict.fromkeys(url for url in urls if url))

    found = {url: _cached(url) for url in unique}

    missing = [url for url in unique if found[url] is None]

    if missing:
        with ThreadPoolExecutor(max_workers=PARALLEL_DOWNLOADS) as pool:
            found.update(zip(missing, pool.map(_fetch_public, missing)))

    for url in missing:
        # The browser fallback only works on the browser's own thread.
        if found.get(url) is None and page is not None:
            found[url] = download_image(page, url)
        _remember(url, found.get(url))

    return found


def images_to_download(display_report):
    """The listing and A+ image links this module (and OCR) may use."""

    display_report = display_report or {}

    listing = (display_report.get("listing_images") or {}).get("images", [])[:MAX_LISTING_IMAGES]
    aplus = (display_report.get("aplus") or {}).get("images", [])[:MAX_APLUS_IMAGES]

    return list(listing) + list(aplus)


def check_aplus_design(page, display_report, images=None):
    """
    Compare the A+ images with the listing images of this product.
    display_report comes from modules/content_display.py.
    images: optional {url: bytes} already downloaded (saves time).
    """

    report = {
        "overall": VERDICT_NOT_CHECKED,
        "rows": [],
        "note": "",
        "listing_images_used": 0
    }

    aplus_urls = (display_report.get("aplus") or {}).get("images", [])[:MAX_APLUS_IMAGES]
    listing_urls = (display_report.get("listing_images") or {}).get("images", [])[:MAX_LISTING_IMAGES]

    if not aplus_urls:
        report["note"] = "No A+ images were found, so there was nothing to compare."
        return report

    # All images are downloaded together, in parallel (unless given).
    if images is None:
        images = download_images(page, list(listing_urls) + list(aplus_urls))

    listing_signatures = []

    for url in listing_urls:
        data = images.get(url)
        if data:
            try:
                listing_signatures.append((url, colour_signature(data)))
            except ValueError:
                pass

    report["listing_images_used"] = len(listing_signatures)

    if not listing_signatures:
        report["note"] = "No listing image could be downloaded, so nothing was compared."
        return report

    aplus_signatures = []

    for url in aplus_urls:
        data = images.get(url)
        signature, reason = None, ""
        if data:
            try:
                signature, info = analyse_image(data)
                reason = skip_reason(info)
            except ValueError:
                signature = None
        aplus_signatures.append((url, signature, reason))

    report["rows"], report["overall"] = compare_signatures(aplus_signatures, listing_signatures)

    skipped = sum(1 for row in report["rows"] if row["Verdict"] == VERDICT_SKIPPED)

    report["note"] = (
        "Colour-based hint, not proof. Check any UNCERTAIN or POSSIBLE "
        "DIFFERENT result by looking at the images side by side. "
        f"{skipped} graphic/text image(s) were skipped."
    )

    return report
