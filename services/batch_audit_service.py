"""
Batch audit service.

Runs the single-product audit for many products, one after another,
and builds the summary table shown on the website.

Blank values from the page are shown as "Not verified", never as an
empty cell, because a blank can mean "not shown" rather than "none".
"""

import json
import re
from datetime import datetime
from pathlib import Path

from modules.amazon_session import AmazonBrowser
from services.audit_service import run_product_audit, finish_image_text


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = PROJECT_ROOT / "exports"

AMAZON_PREFIX = "https://www.amazon.co.uk/"

# Limit per run. Chrome is opened once per run; the next product loads
# in a second tab while the current one is checked.
MAX_LINKS_PER_RUN = 50

# Text shown when the page did not give a value.
NOT_VERIFIED = "Not verified"


def extract_asin(url):
    """Find the 10-character ASIN in an Amazon product link."""

    match = re.search(
        r"/(?:dp|gp/product)/([A-Z0-9]{10})",
        url,
        re.IGNORECASE
    )

    if match:
        return match.group(1).upper()

    return ""


def parse_url_list(raw_text):
    """
    Split pasted text into clean product links.

    Returns two lists:
    - valid: dictionaries with "url" and "asin"
    - rejected: dictionaries with "input" and "reason" (shown to the user)

    Duplicate ASINs are rejected, because the same product audited
    twice gives the same answer and wastes time.
    """

    valid = []
    rejected = []
    seen_asins = set()

    for line in raw_text.splitlines():

        url = line.strip()

        if not url:
            continue

        if not url.startswith(AMAZON_PREFIX):

            rejected.append({
                "input": url,
                "reason": "Not an Amazon UK link"
            })
            continue

        asin = extract_asin(url)

        if not asin:

            rejected.append({
                "input": url,
                "reason": "No ASIN found in this link"
            })
            continue

        if asin in seen_asins:

            rejected.append({
                "input": url,
                "reason": "Duplicate ASIN (already in this list)"
            })
            continue

        seen_asins.add(asin)

        if len(valid) >= MAX_LINKS_PER_RUN:

            rejected.append({
                "input": url,
                "reason": f"Over the {MAX_LINKS_PER_RUN}-link limit per run"
            })
            continue

        valid.append({"url": url, "asin": asin})

    return valid, rejected


def run_batch_audit(items, audit_type="Full Listing Audit", progress_callback=None, spec=None,
                    check_design=False, check_text=False):
    """
    Run the single-product audit for every item, one after another.

    progress_callback(index, total, asin) is called before each product
    so the website can show a progress bar.
    One failed product does not stop the batch; its error is recorded.
    spec: optional specification passed to every product audit.
    check_design: also compare A+ images with listing images.
    check_text: also read the text inside the images (OCR). It runs in
    the background while Chrome loads the next product; the batch only
    waits at the end for anything still being read.
    """

    results = []

    total = len(items)

    def failed(item, message):
        """A result row for a product that could not be audited."""
        return {
            "product_url": item["url"],
            "overall_status": "FAILED",
            "errors": [message],
            "buy_box": {},
            "content": {},
            "spelling": {},
            "spec_check": {},
            "quality": [],
            "asin": item["asin"]
        }

    # Chrome is opened ONCE for the whole batch.
    try:
        browser = AmazonBrowser()
        browser.start()

    except Exception as error:

        return [failed(item, "Browser could not start: " + str(error)) for item in items]

    try:

        for index, item in enumerate(items):

            if progress_callback:
                progress_callback(index, total, item["asin"])

            # The next product starts loading in a second tab as soon as
            # this product's page is ready (see AmazonBrowser.prefetch).
            browser.next_url = items[index + 1]["url"] if index + 1 < total else None
            browser.upcoming = [item["url"] for item in items[index + 1:index + 3]]

            try:

                result = run_product_audit(
                    item["url"], audit_type, spec, browser, check_design,
                    check_text, defer_text=True
                )

            except Exception as error:

                # Record the failure so the table still shows this product,
                # then restart Chrome so the next product gets a clean window.
                result = failed(item, "Unexpected error: " + str(error))

                try:
                    browser.restart()
                except Exception as restart_error:
                    result["errors"].append("Browser restart failed: " + str(restart_error))

            result["asin"] = item["asin"]

            results.append(result)

            # Amazon is not using the saved postcode: every other product
            # would fail the same way, so stop instead of wasting time.
            if result.get("overall_status") == "LOCATION NOT VERIFIED":

                message = (result.get("errors") or ["Location not verified."])[0]

                for skipped in items[index + 1:]:
                    row = failed(skipped, "Not checked. " + message)
                    row["overall_status"] = "LOCATION NOT VERIFIED"
                    results.append(row)

                break

    finally:

        browser.close()

    # Collect the text read from the images in the background.
    for result in results:
        try:
            finish_image_text(result)
        except Exception as error:
            result.setdefault("errors", []).append("Image text failed: " + str(error))

    return results


def build_summary_rows(results):
    """Turn full audit results into one flat row per product."""

    rows = []

    for number, result in enumerate(results, start=1):

        buy_box = result.get("buy_box") or {}
        location = buy_box.get("location") or {}
        content = result.get("content") or {}
        spelling = result.get("spelling") or {}
        summary = spelling.get("summary") or {}
        issues = spelling.get("issues") or []
        spec_check = result.get("spec_check") or {}
        display = result.get("content_display") or {}
        design = result.get("design_check") or {}

        # Names of the places where errors were found, without repeats.
        error_places = []

        for issue in issues:

            place = issue.get("location", "")

            if place and place not in error_places:
                error_places.append(place)

        rows.append({

            "No.": number,

            "ASIN": result.get("asin", ""),

            "Overall Status": result.get("overall_status", ""),

            "Location Verified": "Yes" if location.get("verified") else "No",

            "Price": buy_box.get("price") or NOT_VERIFIED,

            "Seller": buy_box.get("seller") or NOT_VERIFIED,

            "Dispatches From": buy_box.get("dispatches_from") or NOT_VERIFIED,

            "Add to Basket": "Yes" if buy_box.get("add_to_basket_visible") else "No",

            "Featured Offer": buy_box.get("featured_offer_verdict") or NOT_VERIFIED,

            "Listing Images": (
                (display.get("listing_images") or {}).get("count", NOT_VERIFIED)
                if display else NOT_VERIFIED
            ),

            "A+ Content": (display.get("aplus") or {}).get("status") or NOT_VERIFIED,

            "Brand Story": (display.get("brand_story") or {}).get("status") or NOT_VERIFIED,

            "A+ Design": design.get("overall") or "Not checked",

            "Confirmed Errors": summary.get("confirmed_errors", 0),

            "Quality Issues": sum(
                1 for finding in result.get("quality") or []
                if finding.get("severity") in ("High", "Medium", "Low")
            ),

            "Seconds": result.get("seconds", ""),

            "Spec Mismatches": (
                len(spec_check.get("issues", []))
                if spec_check.get("status") == "CHECKED"
                else (spec_check.get("status") or "Not checked")
            ),

            "Where Errors Are": ", ".join(error_places),

            "Problems During Check": "; ".join(result.get("errors", [])),

            "Title": (content.get("title") or "")[:80]

        })

    return rows


def save_batch_report(results, rows):
    """Save the full batch results and summary to a JSON file."""

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    report_path = EXPORT_DIR / f"batch_audit_{timestamp}.json"

    with open(report_path, "w", encoding="utf-8") as file:

        json.dump(
            {"summary_rows": rows, "results": results},
            file,
            indent=4,
            ensure_ascii=False,
            default=str
        )

    return report_path