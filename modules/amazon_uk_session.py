
import json
import re

from pathlib import Path
from playwright.sync_api import sync_playwright


# -----------------------------------------
# PROJECT PATHS
# -----------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROFILE_DIR = PROJECT_ROOT / "data" / "amazon_uk_profile"

EXPORT_DIR = PROJECT_ROOT / "exports"


def get_text(page, selector):
    """Safely extract visible text."""

    try:

        element = page.locator(selector).first

        if element.count() > 0 and element.is_visible():

            return re.sub(
                r"\s+",
                " ",
                element.inner_text()
            ).strip()

    except Exception:
        pass

    return ""


def find_visible_element(page, selectors):
    """Check whether any selector identifies a visible element."""

    for selector in selectors:

        try:

            elements = page.locator(selector)

            for index in range(elements.count()):

                element = elements.nth(index)

                if element.is_visible():

                    return True

        except Exception:

            continue

    return False


def inspect_purchase_area(page):
    """
    Inspect Amazon's purchase buttons and offer information.

    Button presence is not treated as proof of Featured Offer ownership.
    """

    result = {

        "buy_box_container_text": "",

        "add_to_basket_button_found": False,

        "buy_now_button_found": False,

        "purchase_button_status": "NOT VERIFIED",

        "seller_information": "",

        "price": "",

        "featured_offer_status": "NOT VERIFIED"

    }

    # Locate the main purchase area
    buy_box_selectors = [

        "#desktop_buybox",

        "#buybox",

        "#tabular-buybox"

    ]

    for selector in buy_box_selectors:

        text = get_text(page, selector)

        if text:

            result["buy_box_container_text"] = text

            break

    # Add to Basket button
    add_to_basket_selectors = [

        "#add-to-cart-button",

        'input[name="submit.add-to-cart"]',

        "#submit.add-to-cart"

    ]

    result["add_to_basket_button_found"] = (
        find_visible_element(
            page,
            add_to_basket_selectors
        )
    )

    # Buy Now button
    buy_now_selectors = [

        "#buy-now-button",

        'input[name="submit.buy-now"]',

        "#submit.buy-now"

    ]

    result["buy_now_button_found"] = (
        find_visible_element(
            page,
            buy_now_selectors
        )
    )

    # Purchase button assessment
    add_button = result["add_to_basket_button_found"]

    buy_button = result["buy_now_button_found"]

    if add_button and buy_button:

        result["purchase_button_status"] = (
            "BOTH PURCHASE BUTTONS FOUND"
        )

    elif add_button:

        result["purchase_button_status"] = (
            "ADD TO BASKET FOUND"
        )

    elif buy_button:

        result["purchase_button_status"] = (
            "BUY NOW FOUND"
        )

    else:

        result["purchase_button_status"] = (
            "PURCHASE BUTTONS NOT DETECTED"
        )

    # Seller / fulfilment information
    seller_selectors = [

        "#merchant-info",

        "#sellerProfileTriggerId",

        "#tabular-buybox",

        "#fulfiller-info"

    ]

    seller_information = []

    for selector in seller_selectors:

        text = get_text(page, selector)

        if text and text not in seller_information:

            seller_information.append(text)

    result["seller_information"] = " | ".join(
        seller_information
    )

    # Product price
    price_selectors = [

        "#corePrice_feature_div .a-offscreen",

        "#price_inside_buybox",

        "#corePriceDisplay_desktop_feature_div .a-offscreen"

    ]

    for selector in price_selectors:

        price = get_text(page, selector)

        if price:

            result["price"] = price

            break

    # Do not claim Featured Offer verification from buttons alone
    result["featured_offer_status"] = (
        "NOT VERIFIED - seller ownership and offer details "
        "require separate confirmation"
    )

    return result


def setup_uk_delivery_location(product_url, uk_postcode):

    EXPORT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    report = {

        "product_url": product_url,

        "uk_postcode_entered": uk_postcode,

        "location_header": "",

        "postcode_visible_in_header": False,

        "location_status": "NOT VERIFIED",

        "http_status": None,

        "security_challenge": False,

        "purchase_information": {},

        "screenshot": ""

    }

    with sync_playwright() as playwright:

        # Launch a persistent browser profile
        context = playwright.chromium.launch_persistent_context(

            user_data_dir=str(PROFILE_DIR),

            headless=False,

            locale="en-GB",

            timezone_id="Europe/London",

            viewport={
                "width": 1365,
                "height": 900
            }

        )

        try:

            if context.pages:

                page = context.pages[0]

            else:

                page = context.new_page()

            # Open Amazon product page
            response = page.goto(

                product_url,

                wait_until="domcontentloaded",

                timeout=60000

            )

            page.wait_for_timeout(3000)

            if response:

                report["http_status"] = response.status

            # Detect CAPTCHA/security challenge
            body_text = page.locator(
                "body"
            ).inner_text().lower()

            if (

                page.locator("#captchacharacters").count() > 0

                or "sorry, we just need to make sure" in body_text

                or "enter the characters you see below" in body_text

            ):

                report["security_challenge"] = True

                report["location_status"] = (
                    "BLOCKED_OR_CHALLENGE"
                )

                return report

            # Manual location setup instructions
            print("\n==========================================")

            print(" AMAZON UK DELIVERY LOCATION SETUP")

            print("==========================================")

            print("\nYour UK postcode is:")

            print(uk_postcode)

            print("\nFollow these steps in the opened browser:")

            print("\n1. Find 'Deliver to Pakistan' at the top.")

            print("2. Click the delivery location.")

            print("3. Choose Change Address if displayed.")

            print("4. Enter the UK postcode shown above.")

            print("5. Apply or confirm the postcode.")

            print("6. If Amazon shows a list of addresses,")
            print("   select the appropriate delivery location.")

            print("\nDo not select a random address.")

            print("Do not bypass any Amazon security checks.")

            print("\nAfter changing the location:")

            print("Check that Amazon shows your intended")
            print("UK delivery destination in the header.")

            print("\nThe browser will remain open.")

            input(
                "\nAfter completing the location setup, "
                "press ENTER here..."
            )

            # Allow the page to update
            page.wait_for_timeout(3000)

            # Read location header
            report["location_header"] = (

                get_text(
                    page,
                    "#glow-ingress-line2"
                )

                or get_text(
                    page,
                    "#glow-ingress-block"
                )

            )

            normalised_postcode = re.sub(
                r"\s+",
                "",
                uk_postcode
            ).upper()

            normalised_header = re.sub(
                r"\s+",
                "",
                report["location_header"]
            ).upper()

            report["postcode_visible_in_header"] = (
                normalised_postcode in normalised_header
            )

            if report["postcode_visible_in_header"]:

                report["location_status"] = (
                    "POSTCODE VISIBLE IN AMAZON HEADER"
                )

            else:

                report["location_status"] = (
                    "MANUAL CONFIRMATION REQUIRED"
                )

            # Inspect purchase area
            report["purchase_information"] = (
                inspect_purchase_area(page)
            )

            # Save screenshot
            screenshot_path = (
                EXPORT_DIR / "amazon_uk_location_test.png"
            )

            page.screenshot(
                path=str(screenshot_path),
                full_page=False
            )

            report["screenshot"] = str(
                screenshot_path
            )

            # Save JSON report
            report_path = (
                EXPORT_DIR / "uk_location_test.json"
            )

            with open(
                report_path,
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    report,
                    file,
                    indent=4,
                    ensure_ascii=False
                )

            print("\n========== UK LOCATION TEST ==========")

            print(
                json.dumps(
                    report,
                    indent=4,
                    ensure_ascii=False
                )
            )

            print("\nReport saved to:", report_path)

            print("\nBrowser profile saved to:")

            print(PROFILE_DIR)

            print("\n======================================")

        finally:

            context.close()


if __name__ == "__main__":

    print("\n==========================================")

    print(" AMAZON UK LOCATION AND BUY BOX TEST")

    print("==========================================")

    product_url = input(
        "\nEnter Amazon UK product URL: "
    ).strip()

    if not product_url.startswith(
        "https://www.amazon.co.uk/"
    ):

        print("\nInvalid Amazon UK URL.")

    else:

        uk_postcode = input(
            "\nEnter your intended UK delivery postcode: "
        ).strip().upper()

        postcode_pattern = (
            r"^(GIR\s?0AA|[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})$"
        )

        if not re.fullmatch(
            postcode_pattern,
            uk_postcode
        ):

            print(
                "\nThe postcode format does not look like "
                "a standard UK postcode."
            )

            print(
                "Please check the postcode and run again."
            )

        else:

            setup_uk_delivery_location(
                product_url,
                uk_postcode
            )
