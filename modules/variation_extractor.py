
import re
import json
from pathlib import Path
from collections import defaultdict

from playwright.sync_api import sync_playwright


def inspect_radio_option(element):
    """
    Extract information from one Amazon radio control.

    Collects:
    - Accessible label
    - Selected state
    - Option position
    - Expected group size
    - Possible child ASINs
    """

    return element.evaluate("""
        el => {

            // Get accessible label IDs
            const ids = (
                el.getAttribute("aria-labelledby") || ""
            ).split(/\\s+/).filter(Boolean);

            // Find the elements containing the labels
            const labelElements = ids
                .map(id => document.getElementById(id))
                .filter(Boolean);

            const labelText = labelElements
                .map(item =>
                    (item.innerText || item.textContent || "").trim()
                )
                .filter(Boolean)
                .join(" ");

            // Find the option's nearest list item or parent
            const wrapper = el.closest("li") || el.parentElement;

            const wrapperText = wrapper
                ? (wrapper.innerText || "").trim()
                : "";

            // Find possible ASINs on the option and its wrapper
            const asinCandidates = new Set();

            const nodes = [
                el,
                wrapper
            ].filter(Boolean);

            for (const node of nodes) {

                for (const attr of Array.from(node.attributes || [])) {

                    const name = attr.name.toLowerCase();
                    const value = attr.value || "";

                    if (
                        name === "data-asin"
                        || name === "data-defaultasin"
                    ) {

                        if (/^[A-Z0-9]{10}$/i.test(value.trim())) {

                            asinCandidates.add(
                                value.trim().toUpperCase()
                            );

                        }

                    }

                    if (name === "href") {

                        const match = value.match(
                            /\\/(?:dp|gp\\/product)\\/([A-Z0-9]{10})/i
                        );

                        if (match) {

                            asinCandidates.add(
                                match[1].toUpperCase()
                            );

                        }

                    }

                }

            }

            // Choose the best available option label
            const ariaLabel = (
                el.getAttribute("aria-label") || ""
            );

            const title = (
                el.getAttribute("title") || ""
            );

            const label = (
                labelText
                || ariaLabel
                || title
                || wrapperText
            ).trim();

            return {

                "labelled_by": ids,

                "label": label,

                "aria_label": ariaLabel,

                "title": title,

                "wrapper_text": wrapperText.slice(0, 300),

                "name": el.getAttribute("name"),

                "position": el.getAttribute("aria-posinset"),

                "expected_group_size": el.getAttribute(
                    "aria-setsize"
                ),

                "selected": (
                    el.getAttribute("aria-checked") === "true"
                ),

                "disabled": (
                    el.getAttribute("aria-disabled") === "true"
                    || el.disabled === true
                ),

                "visible": !!(
                    el.offsetWidth
                    || el.offsetHeight
                    || el.getClientRects().length
                ),

                "asin_candidates": Array.from(
                    asinCandidates
                ).sort()

            };

        }
    """)


def identify_variation_type(labelled_by):
    """
    Identify variation type from Amazon's accessible label IDs.
    """

    text = " ".join(labelled_by).lower()

    if "color_name" in text or "colour_name" in text:
        return "Colour"

    if "size_name" in text:
        return "Size"

    if "pattern_name" in text:
        return "Pattern"

    if "style_name" in text:
        return "Style"

    return "Unclassified"


def create_group_key(variation_type, option):
    """
    Create a group key.

    Recognised variation types receive their own groups.
    Unknown controls are grouped using normalised label IDs.
    """

    if variation_type != "Unclassified":
        return variation_type

    labelled_by = option.get("labelled_by", [])

    if labelled_by:

        normalised_ids = [

            re.sub(
                r"[_-]\\d+-announce$",
                "-*-announce",
                label_id,
                flags=re.IGNORECASE
            )

            for label_id in labelled_by

        ]

        return "Unclassified: " + " ".join(normalised_ids)

    name = option.get("name") or "unknown"

    return "Unclassified: name=" + name


def extract_variations(product_url):

    report = {

        "product_url": product_url,

        "page_title": "",

        "http_status": None,

        "security_challenge": False,

        "current_asin": "",

        "radio_controls_found": 0,

        "variation_groups": [],

        "child_asins": [],

        "variation_status": "NOT VERIFIED",

        "child_asin_status": "NOT VERIFIED"

    }

    # Extract the current product ASIN from the URL
    asin_match = re.search(
        r"/(?:dp|gp/product)/([A-Z0-9]{10})",
        product_url,
        re.IGNORECASE
    )

    if asin_match:

        report["current_asin"] = (
            asin_match.group(1).upper()
        )

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

                report["variation_status"] = (
                    "BLOCKED_OR_CHALLENGE"
                )

                return report

            # Find the product information area
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

            # Find radio controls inside the product area
            radio_elements = product_area.locator(
                '[role="radio"]'
            )

            total_radios = radio_elements.count()

            report["radio_controls_found"] = (
                total_radios
            )

            # Store options according to their variation groups
            grouped_options = defaultdict(list)

            expected_sizes = defaultdict(int)

            # Inspect each radio control
            for index in range(total_radios):

                element = radio_elements.nth(index)

                try:

                    option = inspect_radio_option(
                        element
                    )

                    labelled_by = option["labelled_by"]

                    variation_type = identify_variation_type(
                        labelled_by
                    )

                    group_key = create_group_key(
                        variation_type,
                        option
                    )

                    option["variation_type"] = (
                        variation_type
                    )

                    # Record Amazon's reported group size
                    try:

                        expected = int(
                            option["expected_group_size"]
                        )

                        expected_sizes[group_key] = max(
                            expected_sizes[group_key],
                            expected
                        )

                    except (TypeError, ValueError):

                        pass

                    # Avoid duplicate options
                    if option not in grouped_options[group_key]:

                        grouped_options[group_key].append(
                            option
                        )

                except Exception as error:

                    print(
                        "Could not inspect radio option:",
                        str(error)
                    )

            # Build the final variation groups
            for group_key, options in grouped_options.items():

                # Identify selected options
                selected_options = [

                    item["label"]

                    for item in options

                    if item["selected"]

                ]

                # Extract possible child ASINs
                discovered_asins = sorted({

                    asin

                    for option in options

                    for asin in option["asin_candidates"]

                    if asin != report["current_asin"]

                })

                # Collect option positions
                positions = sorted({

                    int(option["position"])

                    for option in options

                    if (
                        option["position"]
                        and option["position"].isdigit()
                    )

                })

                expected_count = expected_sizes.get(
                    group_key,
                    0
                )

                detected_count = len(positions)

                if expected_count:

                    if detected_count >= expected_count:

                        coverage_status = (
                            "REPORTED COUNT MATCHED - "
                            "STILL REQUIRES VERIFICATION"
                        )

                    else:

                        coverage_status = (
                            "PARTIAL - MORE OPTIONS MAY EXIST"
                        )

                else:

                    coverage_status = (
                        "UNKNOWN - EXPECTED COUNT NOT PROVIDED"
                    )

                group = {

                    "variation_type": group_key,

                    "detected_options": len(options),

                    "detected_positions": positions,

                    "expected_options": expected_count,

                    "selected_options": selected_options,

                    "child_asins_found": discovered_asins,

                    "coverage_status": coverage_status,

                    "options": options

                }

                report["variation_groups"].append(
                    group
                )

            # Collect all possible child ASINs
            all_child_asins = sorted({

                asin

                for group in report["variation_groups"]

                for option in group["options"]

                for asin in option["asin_candidates"]

                if asin != report["current_asin"]

            })

            report["child_asins"] = all_child_asins

            # Set variation extraction status
            identified_groups = [

                group

                for group in report["variation_groups"]

                if (
                    not group["variation_type"].startswith(
                        "Unclassified"
                    )
                )

            ]

            if identified_groups:

                report["variation_status"] = (
                    "OPTIONS EXTRACTED - "
                    "COVERAGE NOT FULLY VERIFIED"
                )

            elif report["variation_groups"]:

                report["variation_status"] = (
                    "RADIO OPTIONS FOUND - "
                    "GROUPS UNCLASSIFIED"
                )

            else:

                report["variation_status"] = (
                    "NO VARIATION OPTIONS DETECTED - "
                    "ABSENCE NOT VERIFIED"
                )

            # Set child ASIN status
            if all_child_asins:

                report["child_asin_status"] = (
                    "POSSIBLE CHILD ASINS FOUND - VERIFY"
                )

            else:

                report["child_asin_status"] = (
                    "NOT VERIFIED - "
                    "NO CHILD ASINS EXPOSED"
                )

            return report

        finally:

            browser.close()


if __name__ == "__main__":

    print("\n========================================")

    print(" AMAZON VARIATION EXTRACTOR")

    print("========================================")

    url = input(
        "\nEnter Amazon UK Product URL: "
    ).strip()

    if not url.startswith(
        "https://www.amazon.co.uk/"
    ):

        print(
            "\nPlease enter a valid Amazon UK URL."
        )

    else:

        result = extract_variations(url)

        # Create exports directory if necessary
        Path("exports").mkdir(
            parents=True,
            exist_ok=True
        )

        # Save JSON report
        report_path = (
            "exports/variation_report.json"
        )

        with open(
            report_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                result,
                file,
                indent=4,
                ensure_ascii=False
            )

        # Display report
        print("\n========== VARIATION REPORT ==========")

        print(
            json.dumps(
                result,
                indent=4,
                ensure_ascii=False
            )
        )

        print("\nReport saved to:", report_path)

        print("\n======================================")
