
import re
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def clean_text(text):

    if not text:
        return ""

    return re.sub(r"\s+", " ", text).strip()


def inspect_elements(page, selector, limit=25):

    results = []

    locator = page.locator(selector)

    total_found = locator.count()
    visible_count = 0

    for index in range(min(total_found, limit)):

        element = locator.nth(index)

        try:

            if not element.is_visible():
                continue

            visible_count += 1

            details = element.evaluate("""
                element => {

                    const parent =
                        element.closest('[id], [role], li')
                        || element.parentElement;

                    return {

                        tag: element.tagName,

                        id: element.id,

                        role: element.getAttribute('role'),

                        aria_label:
                            element.getAttribute('aria-label'),

                        title:
                            element.getAttribute('title'),

                        text:
                            (element.innerText ||
                             element.textContent || '')
                            .trim()
                            .slice(0, 300),

                        value:
                            element.getAttribute('value'),

                        checked:
                            element.getAttribute('aria-checked'),

                        outer_html:
                            element.outerHTML.slice(0, 1200),

                        parent_html:
                            parent
                                ? parent.outerHTML.slice(0, 1800)
                                : ''

                    };
                }
            """)

            results.append(details)

        except Exception as error:

            results.append({
                "error": str(error)
            })

    return {
        "selector": selector,
        "total_found": total_found,
        "visible_count": visible_count,
        "elements": results
    }


def diagnose_variations(product_url):

    report = {

        "product_url": product_url,

        "page_title": "",

        "http_status": None,

        "security_challenge": False,

        "screenshot": "",

        "variation_controls": [],

        "variation_clues": [],

        "candidate_child_asins": [],

        "overall_status": "NOT VERIFIED"

    }

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

            if response:

                report["http_status"] = response.status

            report["page_title"] = page.title()

            # Detect Amazon security challenges
            body_text = page.locator(
                "body"
            ).inner_text().lower()

            if (
                page.locator("#captchacharacters").count() > 0
                or "sorry, we just need to make sure" in body_text
                or "enter the characters you see below" in body_text
            ):

                report["security_challenge"] = True

                report["overall_status"] = (
                    "BLOCKED_OR_CHALLENGE"
                )

                return report

            # Allow manual inspection in browser
            print("\n========================================")

            print("AMAZON PRODUCT PAGE IS OPEN")

            print("========================================")

            print(
                "\nPlease inspect the opened browser window."
            )

            print(
                "\n1. Dismiss the cookie window using "
                "your preferred option."
            )

            print(
                "2. Scroll through the product page."
            )

            print(
                "3. Look for Size, Colour or Pattern options."
            )

            print(
                "\nDo not change the delivery address."
            )

            input(
                "\nAfter inspecting the page, "
                "press ENTER in this terminal..."
            )

            # Save full-page screenshot
            Path("exports").mkdir(
                parents=True,
                exist_ok=True
            )

            screenshot_path = (
                "exports/variation_page_inspected.png"
            )

            page.screenshot(
                path=screenshot_path,
                full_page=True
            )

            report["screenshot"] = screenshot_path

            # Inspect variation-related controls
            selectors = [

                "#twister",

                "#inline-twister",

                'div[id*="variation" i]',

                'select[id*="variation" i]',

                '[aria-label*="size" i]',

                '[aria-label*="colour" i]',

                '[aria-label*="color" i]',

                '[role="radio"]',

                'input[type="radio"]',

                'button[aria-label]'

            ]

            for selector in selectors:

                inspection = inspect_elements(
                    page,
                    selector
                )

                report["variation_controls"].append(
                    inspection
                )

            # Collect relevant visible product text
            product_area = page.locator(
                "#centerCol"
            )

            if product_area.count() == 0:

                product_area = page.locator(
                    "#dp-container"
                )

            if product_area.count() == 0:

                product_area = page.locator(
                    "body"
                )

            product_text = product_area.inner_text()

            keywords = re.compile(
                r"\b(size|colour|color|pattern|style|"
                r"variation|available options)\b",
                re.IGNORECASE
            )

            for line in product_text.splitlines():

                line = clean_text(line)

                if (
                    line
                    and keywords.search(line)
                    and line not in report["variation_clues"]
                ):

                    report["variation_clues"].append(
                        line[:300]
                    )

            # Find possible child ASIN links
            anchors = product_area.locator(
                'a[href*="/dp/"], '
                'a[href*="/gp/product/"]'
            )

            current_asin_match = re.search(
                r"/(?:dp|gp/product)/([A-Z0-9]{10})",
                product_url,
                re.IGNORECASE
            )

            current_asin = (
                current_asin_match.group(1).upper()
                if current_asin_match
                else ""
            )

            found_asins = set()

            for index in range(
                min(anchors.count(), 150)
            ):

                href = (
                    anchors.nth(index).get_attribute(
                        "href"
                    ) or ""
                )

                match = re.search(
                    r"/(?:dp|gp/product)/([A-Z0-9]{10})",
                    href,
                    re.IGNORECASE
                )

                if match:

                    asin = match.group(1).upper()

                    if asin != current_asin:

                        found_asins.add(asin)

            report["candidate_child_asins"] = sorted(
                found_asins
            )

            # Final diagnostic status
            visible_controls = sum(
                item["visible_count"]
                for item in report["variation_controls"]
            )

            if (
                visible_controls > 0
                or report["candidate_child_asins"]
            ):

                report["overall_status"] = (
                    "POTENTIAL_VARIATION_CONTROLS_FOUND"
                    " - REVIEW REQUIRED"
                )

            else:

                report["overall_status"] = (
                    "NO_VARIATION_CONTROLS_VERIFIED"
                )

            return report

        finally:

            browser.close()


if __name__ == "__main__":

    print("\n========================================")

    print(" AMAZON VARIATION INSPECTOR")

    print("========================================")

    url = input(
        "\nEnter Amazon UK Product URL: "
    ).strip()

    if not url.startswith(
        "https://www.amazon.co.uk/"
    ):

        print("\nPlease enter a valid Amazon UK URL.")

    else:

        result = diagnose_variations(url)

        print("\n========== DIAGNOSTIC RESULTS ==========")

        print(
            json.dumps(
                result,
                indent=4,
                ensure_ascii=False
            )
        )

        print("\n========================================")
