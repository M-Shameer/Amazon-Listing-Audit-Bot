"""
Audit service (orchestrator).

Runs the full product audit from ONE page load:
1. Open the product page and verify the saved Amazon UK postcode.
2. Read the Buy Box / Featured Offer from that page.
3. Read the listing text (title, bullets, description, specifications).
4. A+ content, Brand Story and listing images: displayed or not.
5. Optional: do the A+ images show the same design as the listing?
6. Rules-based spelling check on the extracted text.
7. Listing quality rules (title, bullets, description, images).
8. Optional specification check against your uploaded template.
9. Optional: read the text inside the images (OCR). This runs in a
   background thread; batches collect it at the end (finish_image_text).

Each step's time is recorded in result["timings"] (seconds), and the
total in result["seconds"], so slow steps can be found.

The website (app.py) calls run_product_audit() and only displays
the result. Business logic stays here, not in the interface.
"""

import time
from datetime import datetime

from config.settings_manager import load_settings
from modules.amazon_session import AmazonBrowser
from modules.buybox_audit import read_buy_box_from_page
from modules.listing_content import read_listing_content_from_page
from modules.amazon_extractor import extract_product_images
from modules.content_display import read_content_display, STATUS_NOT_DISPLAYED
from modules.design_match import (
    check_aplus_design,
    download_images,
    images_to_download,
    VERDICT_DIFFERENT,
    VERDICT_UNCERTAIN,
)
from modules.data_cleaner import clean_product_data
from modules.listing_audit import audit_listing
from modules.spec_checker import check_against_spec, amazon_variant_tokens
from modules.quality_rules import check_listing_quality
from modules import image_text
from modules.size_text import check_size_text, page_dimensions
from modules.visual_check import check_visual


class _Timer:
    """Records how long each audit step takes."""

    def __init__(self, result):
        self.result = result
        self.start = time.perf_counter()
        self.last = self.start

    def lap(self, step):
        now = time.perf_counter()
        self.result["timings"][step] = round(now - self.last, 2)
        self.last = now

    def total(self):
        self.result["seconds"] = round(time.perf_counter() - self.start, 1)


def _finish(result, status=None, timer=None):
    """Set the final status (if given), the total time and completion time."""

    if status:
        result["overall_status"] = status

    if timer:
        timer.total()

    result["completed_at"] = datetime.now().astimezone().isoformat()

    return result


def finish_image_text(result):
    """
    Wait for this product's background image reading (if any) and add
    its findings. Safe to call more than once.
    """

    content = result.get("content") or {}

    tokens = amazon_variant_tokens(
        content.get("technical_details") or {},
        {"selections": content.get("variations") or {}, "title": content.get("title", "")}
    )

    return image_text.finish(result, tokens, page_dims=page_dimensions(content))


def content_findings(display, design):
    """
    List the content problems worth a person's attention (pure function).
    Each finding: {"Item", "Status", "Detail"}.
    """

    findings = []

    labels = {
        "listing_images": "Listing images",
        "aplus": "A+ content (EBC)",
        "brand_story": "Brand Story",
    }

    for key, label in labels.items():
        if (display.get(key) or {}).get("status") == STATUS_NOT_DISPLAYED:
            findings.append({
                "Item": label,
                "Status": STATUS_NOT_DISPLAYED,
                "Detail": f"{label} was not found on the live product page. "
                          "Check it in Seller Central."
            })

    overall = (design or {}).get("overall")

    if overall in (VERDICT_DIFFERENT, VERDICT_UNCERTAIN):
        findings.append({
            "Item": "A+ design match",
            "Status": overall,
            "Detail": "One or more A+ images may show a different design "
                      "from the listing images. Compare them by eye."
        })

    return findings


def run_product_audit(product_url, audit_type="Full Listing Audit", spec=None, browser=None,
                      check_design=False, check_text=False, defer_text=False):
    """
    Run the audit for one Amazon UK product.

    spec:    optional specification (services/spec_service.py
             build_spec_for_audit). When given, Amazon's Product
             information table is compared with it.
    browser: an open AmazonBrowser. Batches pass one in so Chrome is
             opened only once. When None, a browser is opened and
             closed just for this product.
    check_design: also compare A+ images with listing images
             (downloads the images, adds a few seconds per product).
    check_text: also read the text inside the images (OCR).
    defer_text: True in batches - the image text is collected later with
             finish_image_text(), so Chrome can load the next product
             while the text is being read.

    Returns one dictionary that the interface can display directly.
    The "errors" list records any step that failed, with the reason.
    """

    if browser is None:

        with AmazonBrowser() as own_browser:
            return run_product_audit(
                product_url, audit_type, spec, own_browser, check_design, check_text
            )

    result = {
        "product_url": product_url,
        "audit_type": audit_type,
        "started_at": datetime.now().astimezone().isoformat(),
        "buy_box": {},
        "content": {},
        "spelling": {},
        "spec_check": {},
        "content_display": {},
        "design_check": {},
        "content_findings": [],
        "quality": [],
        "image_text": {},
        "visual": {},
        "timings": {},
        "seconds": None,
        "overall_status": "NOT COMPLETED",
        "errors": []
    }

    timer = _Timer(result)

    # STEP 1: Open the page once and verify the delivery location.
    try:

        page, location = browser.open_product(product_url)

    except Exception as error:

        result["errors"].append("The product page could not be opened: " + str(error))

        return _finish(result, "FAILED", timer)

    timer.lap("Open page")

    # STEP 2: Buy Box / Featured Offer from the same page.
    try:

        expected_seller = load_settings().get("expected_seller", "")

        buy_box = read_buy_box_from_page(page, location, expected_seller)

        buy_box["product_url"] = product_url

        result["buy_box"] = buy_box

    except Exception as error:

        result["errors"].append("Buy Box check failed: " + str(error))

        return _finish(result, "FAILED", timer)

    timer.lap("Buy Box")

    # Stop if Amazon is not using the saved postcode (or blocked us).
    # Prices and delivery from the wrong location must not be reported.
    if location.get("security_challenge"):

        result["errors"].append(
            "Amazon showed a security check. It was not bypassed, "
            "so nothing was read."
        )

        return _finish(result, "BLOCKED BY AMAZON", timer)

    if not location.get("verified"):

        result["errors"].append(
            location.get("help")
            or "Amazon location is not verified. Listing results were not checked."
        )

        return _finish(result, "LOCATION NOT VERIFIED", timer)

    # STEP 3: Listing text from the same page.
    try:

        content = read_listing_content_from_page(page, location, product_url)

        result["content"] = content

    except Exception as error:

        result["errors"].append("Listing extraction failed: " + str(error))

        return _finish(result, "PARTIAL - EXTRACTION FAILED", timer)

    timer.lap("Listing text")

    if content.get("status") != "EXTRACTED":

        result["errors"].append(
            "Listing content status: " + str(content.get("status"))
        )

    # STEP 4: A+ content, Brand Story and listing images (same page).
    try:

        result["content_display"] = read_content_display(
            page, location, extract_product_images(page)
        )

    except Exception as error:

        result["errors"].append("Content display check failed: " + str(error))

    timer.lap("A+ / images")

    # STEP 5: Download the images ONCE (for the design check and OCR).
    display = result["content_display"] or {}

    images = {}

    if (check_design or check_text) and display:

        try:
            images = download_images(page, images_to_download(display))
        except Exception as error:
            result["errors"].append("Image download failed: " + str(error))

        timer.lap("Download images")

    # STEP 5a: Optional A+ design match.
    if check_design and display:

        try:
            result["design_check"] = check_aplus_design(page, display, images)
        except Exception as error:
            result["errors"].append("A+ design check failed: " + str(error))

        timer.lap("A+ design")

    # STEP 5c: Colour name and videos vs listing images (with the design check).
    if check_design and display:

        try:
            result["visual"] = check_visual(page, content, display, images)
        except Exception as error:
            result["errors"].append("Colour / video check failed: " + str(error))

        timer.lap("Colour + video")

    # STEP 5b: Optional text inside images, read in the background.
    if check_text and display:
        result["_image_text_future"] = image_text.start_reading(display, images)

    result["content_findings"] = content_findings(
        result["content_display"], result["design_check"]
    )

    # STEP 6: Spelling and rules check.
    # clean_product_data removes script noise and duplicate images.
    cleaned = {}

    try:

        cleaned = clean_product_data(content)

        result["spelling"] = audit_listing(cleaned)

    except Exception as error:

        result["errors"].append("Spelling check failed: " + str(error))

    # STEP 7: Listing quality rules (title, bullets, description, images).
    image_count = (display.get("listing_images") or {}).get("count") if display else None

    aplus_displayed = (display.get("aplus") or {}).get("status") not in (None, STATUS_NOT_DISPLAYED)

    result["quality"] = check_listing_quality(content, image_count, aplus_displayed)

    # Sizes written the same way everywhere on the page.
    result["quality"] += check_size_text(content)

    timer.lap("Spelling + quality")

    # STEP 8: Specification check (only when a specification was chosen).
    if spec:

        try:

            result["spec_check"] = check_against_spec(
                cleaned.get("technical_details") or {},
                spec,
                variant_info={
                    "selections": content.get("variations") or {},
                    "title": content.get("title", ""),
                    "bullets": content.get("bullets") or [],
                    "description": content.get("description", ""),
                }
            )

        except Exception as error:

            result["errors"].append("Specification check failed: " + str(error))

    # Plain summary status for the interface.
    summary = result["spelling"].get("summary", {})

    confirmed = (
        summary.get("confirmed_errors", 0)
        + len(result["spec_check"].get("issues", []))
        + len(result["content_findings"])
        + sum(1 for finding in result["quality"] if finding["severity"] in ("High", "Medium"))
    )

    if result["errors"]:
        status = "COMPLETED WITH WARNINGS"
    elif confirmed:
        status = "ISSUES FOUND"
    else:
        status = "NO RULE-BASED ISSUES FOUND"

    _finish(result, status, timer)

    # A single product (not a batch) waits for its image text here.
    if not defer_text:
        finish_image_text(result)

    return result
