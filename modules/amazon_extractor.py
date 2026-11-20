
import re
import json
from playwright.sync_api import sync_playwright


def clean_text(text):
    """Remove unnecessary spaces and line breaks."""

    if not text:
        return ""

    return re.sub(r"\s+", " ", text).strip()


def get_text(page, selector):
    """Safely extract text from the first matching element."""

    try:
        element = page.locator(selector).first

        if element.count() > 0:
            return clean_text(element.inner_text())

    except Exception:
        pass

    return ""


def get_attribute(element, attribute):
    """Safely extract an HTML attribute."""

    try:
        return element.get_attribute(attribute) or ""

    except Exception:
        return ""


# Reads EVERY Product information row, including Amazon's newer layout
# (collapsible "Item details / Measurements / Style / Materials & Care"
# sections). textContent is used because collapsed sections are hidden,
# and hidden text is not returned by inner_text().
_DETAILS_JS = """
() => {
    const out = {};
    const clean = t => (t || '')
        .replace(/[\\u200e\\u200f\\u202a-\\u202e]/g, '')
        .replace(/\\s+/g, ' ')
        .trim();
    const roots = document.querySelectorAll([
        '#prodDetails', '#productDetails_feature_div', '[id^="productDetails_"]',
        '#productOverview_feature_div', '#detailBullets_feature_div',
        '#technicalSpecifications_feature_div', '#tech', '#productFactsDesktopExpander',
        '#poExpander', '#product-facts-feature-div'
    ].join(','));
    roots.forEach(root => {
        root.querySelectorAll('tr').forEach(tr => {
            const cells = Array.from(tr.querySelectorAll('th, td'))
                .map(cell => clean(cell.textContent)).filter(Boolean);
            if (cells.length >= 2 && cells[0].length <= 80) {
                const key = cells[0].replace(/[\\s:]+$/, '');
                if (key && !(key in out)) out[key] = cells.slice(1).join(' | ');
            }
        });
        root.querySelectorAll('li').forEach(li => {
            const bold = li.querySelector('.a-text-bold');
            if (!bold) return;
            const label = clean(bold.textContent);
            const key = label.replace(/[\\s:]+$/, '');
            const value = clean(clean(li.textContent).replace(label, '')).replace(/^[\\s:]+/, '');
            if (key && value && key.length <= 80 && !(key in out)) out[key] = value;
        });
    });
    return out;
}
"""


def extract_technical_details(page):
    """
    Extract the Product information of the page: {field name: value}.

    1. One JavaScript pass reads every table row and detail bullet in
       all Product information areas, including collapsed sections.
    2. The older method fills in anything the first pass missed.
    """

    technical_details = {}

    try:
        found = page.evaluate(_DETAILS_JS) or {}
        technical_details = {
            clean_text(key): clean_text(value)
            for key, value in found.items()
            if clean_text(key) and clean_text(value)
        }
    except Exception:
        technical_details = {}

    for key, value in _extract_visible_details(page).items():
        technical_details.setdefault(key, value)

    return technical_details


def _extract_visible_details(page):
    """Older method: visible specification tables and detail bullets."""

    technical_details = {}

    table_selectors = [
        "#productDetails_techSpec_section_1 tr",
        "#productDetails_detailBullets_sections1 tr",
        "#productDetails_db_sections tr",
        "#productDetails_feature_div table tr"
    ]

    for selector in table_selectors:

        try:
            rows = page.locator(selector).all()

            for row in rows:

                cells = [
                    clean_text(value)
                    for value in row.locator("th, td").all_inner_texts()
                ]

                cells = [value for value in cells if value]

                if len(cells) >= 2:

                    key = cells[0]
                    value = " | ".join(cells[1:])

                    if key and value:
                        technical_details[key] = value

        except Exception:
            continue

    try:

        detail_items = page.locator("#detailBullets_feature_div li").all()

        for item in detail_items:

            try:
                label_element = item.locator("span.a-text-bold").first

                if label_element.count() == 0:
                    continue

                label = clean_text(label_element.inner_text())

                full_text = clean_text(item.inner_text())

                value = clean_text(full_text.replace(label, "", 1).strip(" :"))

                if label and value:
                    technical_details[label] = value

            except Exception:
                continue

    except Exception:
        pass

    return technical_details


def extract_product_images(page):
    """
    Extract the main image and additional product gallery images.

    Also checks Amazon's dynamic image data when available.
    """

    images = []

    def add_image(url):

        if not url:
            return

        url = url.strip()

        if (
            url.startswith("https://")
            and url not in images
            and not url.startswith("data:")
        ):
            images.append(url)

    # Main product image
    try:

        main_image = page.locator(
            "#landingImage"
        ).first

        if main_image.count() > 0:

            add_image(
                get_attribute(main_image, "data-old-hires")
            )

            add_image(
                get_attribute(main_image, "src")
            )

            # Extract URLs from dynamic image JSON
            dynamic_data = get_attribute(
                main_image,
                "data-a-dynamic-image"
            )

            if dynamic_data:

                try:
                    image_data = json.loads(dynamic_data)

                    for image_url in image_data.keys():
                        add_image(image_url)

                except (json.JSONDecodeError, AttributeError):
                    pass

    except Exception:
        pass

    # Additional gallery images
    try:

        gallery_images = page.locator(
            "#altImages img"
        ).all()

        for image in gallery_images:

            add_image(
                get_attribute(image, "data-old-hires")
            )

            add_image(
                get_attribute(image, "src")
            )

            add_image(
                get_attribute(image, "data-src")
            )

    except Exception:
        pass

    return images


def extract_variations(page):
    """
    Extract visible variation groups without clicking or
    changing the selected product variation.
    """

    variations = []

    try:

        containers = page.locator(
            'div[id^="variation_"]'
        ).all()

        for container in containers:

            try:

                if not container.is_visible():
                    continue

                group_id = get_attribute(
                    container,
                    "id"
                )

                # Determine variation group name
                label = ""

                for selector in [
                    ".a-form-label",
                    "label",
                    "legend"
                ]:

                    label = get_text(
                        container,
                        selector
                    )

                    if label:
                        break

                if not label:
                    label = group_id.replace(
                        "variation_", ""
                    ).replace("_", " ").title()

                options = []

                option_elements = container.locator(
                    "li, option"
                ).all()

                for option in option_elements:

                    try:

                        value = (
                            get_attribute(option, "title")
                            or get_attribute(option, "aria-label")
                            or clean_text(option.inner_text())
                        )

                        # Try to find an image description
                        if not value:

                            image = option.locator("img").first

                            if image.count() > 0:
                                value = get_attribute(
                                    image,
                                    "alt"
                                )

                        if not value:
                            continue

                        # Extract variation ASIN if available
                        variation_asin = get_attribute(
                            option,
                            "data-asin"
                        )

                        if not variation_asin:

                            asin_element = option.locator(
                                "[data-asin]"
                            ).first

                            if asin_element.count() > 0:

                                variation_asin = get_attribute(
                                    asin_element,
                                    "data-asin"
                                )

                        # Check whether this is selected
                        classes = (
                            get_attribute(option, "class")
                        )

                        aria_checked = get_attribute(
                            option,
                            "aria-checked"
                        )

                        selected = (
                            "swatchSelect" in classes
                            or aria_checked == "true"
                        )

                        option_data = {
                            "value": value,
                            "asin": variation_asin,
                            "selected": selected
                        }

                        # Avoid duplicate options
                        if option_data not in options:
                            options.append(option_data)

                    except Exception:
                        continue

                if options:

                    variations.append({
                        "variation_type": label,
                        "options": options
                    })

            except Exception:
                continue

    except Exception:
        pass

    return variations


def extract_amazon_product(product_url):
    """
    Extract customer-facing product information from
    an Amazon UK product page.

    This function does not bypass CAPTCHA or other
    Amazon security restrictions.
    """

    product_data = {

        "url": product_url,

        "asin": "",

        "title": "",

        "price": "",

        "bullets": [],

        "description": "",

        "technical_details": {},

        "technical_details_status": "NOT VERIFIED",

        "image_url": "",

        "images": [],

        "images_status": "NOT VERIFIED",

        "variations": [],

        "variation_status": "NOT VERIFIED",

        "availability": "",

        "delivery_info": "",

        "buy_box_text": "",

        "buy_box_status": "NOT VERIFIED",

        "image_text": [],

        "extraction_status": "NOT VERIFIED"
    }

    # Extract ASIN from product URL
    asin_match = re.search(
        r"/(?:dp|gp/product)/([A-Z0-9]{10})",
        product_url,
        re.IGNORECASE
    )

    if asin_match:

        product_data["asin"] = asin_match.group(
            1
        ).upper()

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=False
        )

        try:

            page = browser.new_page(
                locale="en-GB",
                timezone_id="Europe/London"
            )

            response = page.goto(
                product_url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(3000)

            # Check HTTP response
            if response and response.status >= 400:

                print(
                    "Amazon returned HTTP status:",
                    response.status
                )

                return product_data

            # Detect possible CAPTCHA/security page
            page_text = get_text(
                page,
                "body"
            ).lower()

            challenge_detected = (
                page.locator("#captchacharacters").count() > 0
                or "sorry, we just need to make sure" in page_text
                or "enter the characters you see below" in page_text
            )

            if challenge_detected:

                product_data["extraction_status"] = (
                    "BLOCKED_OR_CHALLENGE"
                )

                print(
                    "Amazon security challenge detected. "
                    "No attempt will be made to bypass it."
                )

                return product_data

            # --------------------------------
            # 1. PRODUCT TITLE
            # --------------------------------

            product_data["title"] = get_text(
                page,
                "#productTitle"
            )

            # --------------------------------
            # 2. PRODUCT PRICE
            # --------------------------------

            product_data["price"] = get_text(
                page,
                ".a-price .a-offscreen"
            )

            # --------------------------------
            # 3. BULLET POINTS
            # --------------------------------

            try:

                bullets = page.locator(
                    "#feature-bullets li .a-list-item"
                ).all_inner_texts()

                product_data["bullets"] = [
                    clean_text(bullet)
                    for bullet in bullets
                    if clean_text(bullet)
                ]

            except Exception:
                pass

            # --------------------------------
            # 4. PRODUCT DESCRIPTION
            # --------------------------------

            product_data["description"] = get_text(
                page,
                "#productDescription"
            )

            # --------------------------------
            # 5. TECHNICAL DETAILS
            # --------------------------------

            technical_details = extract_technical_details(
                page
            )

            product_data["technical_details"] = (
                technical_details
            )

            if technical_details:

                product_data["technical_details_status"] = (
                    "EXTRACTED"
                )

            # --------------------------------
            # 6. PRODUCT IMAGES
            # --------------------------------

            images = extract_product_images(
                page
            )

            product_data["images"] = images

            if images:

                product_data["image_url"] = images[0]

                product_data["images_status"] = (
                    "EXTRACTED"
                )

            # --------------------------------
            # 7. PRODUCT VARIATIONS
            # --------------------------------

            variations = extract_variations(
                page
            )

            product_data["variations"] = variations

            if variations:

                product_data["variation_status"] = (
                    "OPTIONS FOUND - VERIFY COVERAGE"
                )

            # --------------------------------
            # 8. AVAILABILITY
            # --------------------------------

            product_data["availability"] = get_text(
                page,
                "#availability"
            )

            # --------------------------------
            # 9. DELIVERY INFORMATION
            # --------------------------------

            delivery_selectors = [
                "#mir-layout-DELIVERY_BLOCK",
                "#deliveryBlockMessage",
                "#deliveryBlock_feature_div"
            ]

            for selector in delivery_selectors:

                delivery_text = get_text(
                    page,
                    selector
                )

                if delivery_text:

                    product_data["delivery_info"] = (
                        delivery_text
                    )

                    break

            # --------------------------------
            # 10. FEATURED OFFER / BUY BOX
            # --------------------------------

            buy_box_selectors = [
                "#desktop_buybox",
                "#buybox",
                "#tabular-buybox",
                "#offerDisplayFeatures_feature_div"
            ]

            for selector in buy_box_selectors:

                buy_box_text = get_text(
                    page,
                    selector
                )

                if buy_box_text:

                    product_data["buy_box_text"] = (
                        buy_box_text
                    )

                    product_data["buy_box_status"] = (
                        "TEXT EXTRACTED - OFFER NOT VERIFIED"
                    )

                    break

            # --------------------------------
            # 11. EXTRACTION STATUS
            # --------------------------------

            if product_data["title"]:

                product_data["extraction_status"] = (
                    "SUCCESS"
                )

            else:

                product_data["extraction_status"] = (
                    "PARTIAL"
                )

            return product_data

        finally:

            browser.close()


# --------------------------------------------
# TEST THE EXTRACTOR DIRECTLY
# --------------------------------------------

if __name__ == "__main__":

    url = input(
        "Enter your Amazon UK product URL: "
    ).strip()

    if not url.startswith(
        "https://www.amazon.co.uk/"
    ):

        print(
            "Please enter a valid Amazon UK product URL."
        )

    else:

        result = extract_amazon_product(
            url
        )

        print(
            "\n========== PRODUCT EXTRACTION RESULT =========="
        )

        print(
            json.dumps(
                result,
                indent=4,
                ensure_ascii=False
            )
        )

        print(
            "\n==============================================="
        )
