"""
Listing content extractor.

Reads the customer-facing text of an Amazon UK product page
(title, bullets, description, specifications, availability).

read_listing_content_from_page() reads a page that is ALREADY open,
so the audit can read the Buy Box and the text from one page load.
extract_listing_content() is kept for tools that open a single page.

It reuses extract_technical_details from amazon_extractor.py instead
of copying it, so the logic exists in only one place.
"""

import re
from datetime import datetime

from modules.amazon_session import open_verified_amazon_page
from modules.amazon_extractor import extract_technical_details


def clean_text(text):
    """Collapse spaces and line breaks into single spaces."""

    if not isinstance(text, str):
        return ""

    return re.sub(r"\s+", " ", text).strip()


def get_text(page, selector):
    """
    Return the text of the first matching element, or "" if
    it does not exist. Never raises an error for a missing element.
    """

    try:

        element = page.locator(selector).first

        if element.count() > 0:

            return clean_text(
                element.inner_text(timeout=3000)
            )

    except Exception:
        pass

    return ""


def read_listing_content_from_page(page, location, product_url=""):
    """
    Read the listing text from a page that is already open.

    Status values:
    - EXTRACTED: title was found and the text was read.
    - PARTIAL: the page opened, but no title was found.
    - LOCATION NOT VERIFIED: Amazon is not using the saved postcode.
    - BLOCKED_OR_CHALLENGE: Amazon showed a security check.

    A missing field is recorded as empty. It is not treated as
    proof that the listing has no such field.
    """

    content = {
        "product_url": product_url,
        "extracted_at": datetime.now().astimezone().isoformat(),
        "location": location,
        "title": "",
        "bullets": [],
        "description": "",
        "technical_details": {},
        "variations": {},
        "size_options": [],
        "availability": "",
        "status": "NOT VERIFIED"
    }

    if location.get("security_challenge"):
        content["status"] = "BLOCKED_OR_CHALLENGE"
        return content

    if not location.get("verified"):
        content["status"] = "LOCATION NOT VERIFIED"
        return content

    # 1. Title
    content["title"] = get_text(page, "#productTitle")

    # 2. Bullet points
    try:

        raw_bullets = page.locator(
            "#feature-bullets li .a-list-item"
        ).all_inner_texts()

        content["bullets"] = [
            clean_text(bullet)
            for bullet in raw_bullets
            if clean_text(bullet)
        ]

    except Exception:
        # Keep the empty list; the audit records the gap.
        pass

    # 3. Product description (may be empty on some listings)
    content["description"] = get_text(page, "#productDescription")

    # 4. Specifications (size, material, colour and so on)
    content["technical_details"] = extract_technical_details(page)

    # 5. Availability
    content["availability"] = get_text(page, "#availability")

    # 6. Selected variation buttons, e.g. {"size_name": "Double",
    #    "style_name": "4 Piece"}. Used to pick the template row.
    content["variations"] = read_selected_variations(page)

    # 7. The text of EVERY size button / size list entry (for the
    #    size text consistency check).
    content["size_options"] = read_size_options(page)

    content["status"] = "EXTRACTED" if content["title"] else "PARTIAL"

    return content


# Reads the selected value of every variation group on the page
# (classic "variation_*" blocks and the newer inline twister).
_VARIATIONS_JS = """
() => {
    const out = {};
    document.querySelectorAll('[id^="variation_"] .selection').forEach(el => {
        const holder = el.closest('[id^="variation_"]');
        const text = (el.textContent || '').trim();
        if (holder && text) out[holder.id.replace('variation_', '')] = text;
    });
    document.querySelectorAll('[id^="inline-twister-expanded-dimension-text-"]').forEach(el => {
        const text = (el.textContent || '').trim();
        if (text) out[el.id.replace('inline-twister-expanded-dimension-text-', '')] = text;
    });
    return out;
}
"""


# Text of every size choice on the page (buttons, list, drop-down).
_SIZE_OPTIONS_JS = """
() => {
    const seen = new Set();
    const out = [];
    const selector = [
        '[id*="size_name"] li', '[id*="size_name"] option',
        '[id*="size_name"] .swatch-title-text', '[id*="size_name"] .a-button-text'
    ].join(',');
    document.querySelectorAll(selector).forEach(el => {
        const text = (el.getAttribute('title') || el.textContent || '')
            .replace(/^Click to select\\s*/i, '').replace(/\\s+/g, ' ').trim();
        if (text && text.length <= 120 && !seen.has(text)) {
            seen.add(text);
            out.push(text);
        }
    });
    return out.slice(0, 40);
}
"""


def read_size_options(page):
    """Return the text of every size choice; [] if none or on error."""

    try:
        return [clean_text(text) for text in (page.evaluate(_SIZE_OPTIONS_JS) or [])]
    except Exception:
        return []


def read_selected_variations(page):
    """Return {variation name: selected value}; {} if none or on error."""

    try:
        found = page.evaluate(_VARIATIONS_JS)
        return {str(key): clean_text(value) for key, value in (found or {}).items()}
    except Exception:
        return {}


def extract_listing_content(product_url):
    """Open one product page and read its listing text."""

    with open_verified_amazon_page(product_url) as (page, location):

        return read_listing_content_from_page(page, location, product_url)
