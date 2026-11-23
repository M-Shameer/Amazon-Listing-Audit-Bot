"""
Content display check: listing images, A+ content (EBC) and Brand Story.

Reads a product page that is ALREADY open (no extra page load) and
records, for each part, whether it is displayed and which images it
uses. Nothing is clicked.

Statuses:
- DISPLAYED      found on the page with content
- NOT DISPLAYED  the page loaded fully but the section was not found
                 or was empty (worth checking in Seller Central)
- NOT VERIFIED   the page could not be read (location or security)
"""

import re


STATUS_DISPLAYED = "DISPLAYED"
STATUS_NOT_DISPLAYED = "NOT DISPLAYED"
STATUS_NOT_VERIFIED = "NOT VERIFIED"

# Where Amazon puts each part of the page.
APLUS_SELECTORS = ["#aplus_feature_div", "#aplus", "#aplus3p_feature_div"]
BRAND_STORY_SELECTORS = ["#aplusBrandStory_feature_div"]
SCROLL_TARGETS = ["#aplusBrandStory_feature_div", "#aplus_feature_div", "#aplus"]

# Images smaller than this on screen are icons or logos, not photos.
MIN_IMAGE_WIDTH = 120
MIN_IMAGE_HEIGHT = 80

# One JavaScript call collects everything, which is much faster than
# asking for each element separately. For every image it records the
# address, whether it is visible on screen (premium A+ also contains
# hidden copies for phones) and its size on screen.
_COLLECT_JS = r"""
(selectors) => {
    const pick = (img) =>
        img.getAttribute("data-src")
        || img.getAttribute("data-a-hires")
        || img.getAttribute("src")
        || "";

    const section = (list, excludeSelector) => {
        for (const selector of list) {
            const root = document.querySelector(selector);
            if (!root) continue;

            const images = Array.from(root.querySelectorAll("img"))
                .filter(img => !excludeSelector || !img.closest(excludeSelector))
                .map(img => {
                    const box = img.getBoundingClientRect();
                    const style = window.getComputedStyle(img);
                    return {
                        url: pick(img),
                        w: Math.round(box.width),
                        h: Math.round(box.height),
                        visible: box.width > 0 && box.height > 0
                                 && style.display !== "none"
                                 && style.visibility !== "hidden"
                    };
                });

            const modules = root.querySelectorAll(
                ".aplus-module, .premium-aplus-module"
            ).length;

            const text = (root.innerText || "").replace(/\s+/g, " ").trim();

            return {found: true, selector, images, modules, text_length: text.length,
                    text_sample: text.slice(0, 300)};
        }
        return {found: false, selector: "", images: [], modules: 0,
                text_length: 0, text_sample: ""};
    };

    // Brand Story sits inside the A+ area on some pages; keep them apart.
    return {
        aplus: section(selectors.aplus, "#aplusBrandStory_feature_div"),
        brand_story: section(selectors.brand_story, null)
    };
}
"""


def is_content_image(url, allow_aplus_media=True):
    """
    True for real product/A+ images; False for icons, sprites, pixels
    and video play buttons.
    """

    url = str(url or "")

    if not url.startswith("https://"):
        return False

    lower = url.lower()

    if lower.endswith(".gif") or any(
        word in lower for word in ("pixel", "sprite", "play-button", "transparent")
    ):
        return False

    if "/images/i/" in lower:
        return True

    return allow_aplus_media and "/images/s/aplus-media" in lower


def image_key(url):
    """
    The underlying image name, the same for every size of one image:
    .../I/71abc._AC_SL1500_.jpg and .../I/71abc._AC_US40_.jpg -> "71abc"
    .../aplus-media.../1a2b.__CR0,0,970,600_...jpg            -> "1a2b"
    """

    filename = str(url).split("?")[0].rstrip("/").rsplit("/", 1)[-1]

    return filename.split(".", 1)[0]


def _as_item(entry):
    """Accept a plain URL or the dictionary sent by the page."""

    if isinstance(entry, dict):
        return {
            "url": entry.get("url", ""),
            "w": entry.get("w") or 0,
            "h": entry.get("h") or 0,
            "visible": bool(entry.get("visible", True))
        }

    return {"url": entry, "w": 0, "h": 0, "visible": True}


def unique_images(entries, allow_aplus_media=True):
    """
    Keep real, visible, photo-sized images, one URL per image.

    - Hidden copies (e.g. A+ images meant for phones) are dropped,
      unless nothing is visible yet (then all are kept).
    - Images shown smaller than MIN_IMAGE_WIDTH x MIN_IMAGE_HEIGHT are
      icons or logos and are dropped. Unknown sizes (0) are kept.
    - Different sizes of the same image count once.
    """

    items = [
        item for item in map(_as_item, entries)
        if is_content_image(item["url"], allow_aplus_media)
    ]

    visible = [item for item in items if item["visible"]]

    pool = visible if visible else items

    def big_enough(item):
        unknown = item["w"] == 0 and item["h"] == 0
        return unknown or (item["w"] >= MIN_IMAGE_WIDTH and item["h"] >= MIN_IMAGE_HEIGHT)

    seen = set()
    result = []

    for item in pool:

        if not big_enough(item):
            continue

        key = image_key(item["url"])

        if key in seen:
            continue

        seen.add(key)
        result.append(item["url"])

    return result


def section_status(section, page_ok):
    """DISPLAYED / NOT DISPLAYED / NOT VERIFIED for one section."""

    if not page_ok:
        return STATUS_NOT_VERIFIED

    has_content = (
        section.get("images")
        or section.get("modules", 0) > 0
        or section.get("text_length", 0) > 40
    )

    return STATUS_DISPLAYED if section.get("found") and has_content else STATUS_NOT_DISPLAYED


def summarise_display(raw, listing_urls, page_ok):
    """
    Turn raw page data into the report (pure function, unit tested).

    raw: {"aplus": {...}, "brand_story": {...}} from the page
    listing_urls: image URLs from the main image and gallery
    """

    listing = unique_images(listing_urls, allow_aplus_media=False)

    aplus = dict(raw.get("aplus") or {})
    aplus["images"] = unique_images(aplus.get("images", []))

    brand = dict(raw.get("brand_story") or {})
    brand["images"] = unique_images(brand.get("images", []))

    report = {
        "listing_images": {
            "status": (
                STATUS_NOT_VERIFIED if not page_ok
                else STATUS_DISPLAYED if listing else STATUS_NOT_DISPLAYED
            ),
            "count": len(listing),
            "main_image": listing[0] if listing else "",
            "images": listing
        },
        "aplus": {
            "status": section_status(aplus, page_ok),
            "modules": aplus.get("modules", 0),
            "image_count": len(aplus["images"]),
            "images": aplus["images"],
            "text_sample": aplus.get("text_sample", ""),
            "source": aplus.get("selector", "")
        },
        "brand_story": {
            "status": section_status(brand, page_ok),
            "image_count": len(brand["images"]),
            "images": brand["images"],
            "source": brand.get("selector", "")
        }
    }

    return report


def read_content_display(page, location, listing_urls):
    """
    Read A+, Brand Story and image information from an open page.
    listing_urls comes from amazon_extractor.extract_product_images().
    """

    page_ok = bool(location.get("verified")) and not location.get("security_challenge")

    raw = {"aplus": {}, "brand_story": {}}

    if page_ok:

        # A+ and Brand Story sit low on the page; scroll there once so
        # lazily loaded parts appear. Nothing is clicked.
        for selector in SCROLL_TARGETS:
            try:
                target = page.locator(selector).first
                if target.count() > 0:
                    target.scroll_into_view_if_needed(timeout=3000)
                    page.wait_for_timeout(200)
            except Exception:
                continue

        try:
            raw = page.evaluate(
                _COLLECT_JS,
                {"aplus": APLUS_SELECTORS, "brand_story": BRAND_STORY_SELECTORS}
            )
        except Exception:
            raw = {"aplus": {}, "brand_story": {}}

        try:
            page.evaluate("window.scrollTo(0, 0)")
        except Exception:
            pass

    return summarise_display(raw, listing_urls, page_ok)


def clean_sample(text):
    """Short, single-line text for tables."""

    return re.sub(r"\s+", " ", str(text or "")).strip()[:120]
