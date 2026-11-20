"""
Variation service.

Reads the colour and size options of an Amazon UK product family so one
size can be audited across all of its colours.

Amazon's product page contains two useful tables:
1. "dimensionValuesDisplayData": ASIN -> [colour, size]. This is the
   preferred source, because each ASIN is named directly.
2. "dimensionToAsinMap" + "variationValues": a fallback that joins index
   keys such as "4_15" to label lists. It is used only if table 1 is missing.

Nothing is clicked, and the selected variation is not changed.
"""

import json
import re
from datetime import datetime

from modules.amazon_session import open_verified_amazon_page


def find_block_end(html, start):
    """
    Return the position just after the JSON block that starts at `start`.
    Brackets inside quoted text are skipped, so a "{" in a product name
    cannot end the block early. Returns -1 if the block never closes.
    """

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(html)):

        char = html[index]

        if in_string:

            if escaped:
                escaped = False

            elif char == "\\":
                escaped = True

            elif char == '"':
                in_string = False

            continue

        if char == '"':
            in_string = True

        elif char in "{[":
            depth += 1

        elif char in "}]":
            depth -= 1

            if depth == 0:
                return index + 1

    return -1


def read_json_value(html, key, expected_type):
    """
    Find "key" : followed by a JSON object (dict) or list (list) in the
    page HTML and return it as Python data.

    The key may appear several times on the page, so every match is
    tried, and the first one that parses to a non-empty value is used.
    Returns None if nothing suitable is found.
    """

    pattern = re.compile(r'"' + re.escape(key) + r'"\s*:\s*')

    for match in pattern.finditer(html):

        start = match.end()

        if start >= len(html):
            continue

        opener = html[start]

        if expected_type is dict and opener != "{":
            continue

        if expected_type is list and opener != "[":
            continue

        end = find_block_end(html, start)

        if end == -1:
            continue

        try:
            value = json.loads(html[start:end])

        except json.JSONDecodeError:
            continue

        if isinstance(value, expected_type) and value:
            return value

    return None


def read_total_variations(html):
    """Read Amazon's reported total number of variations, or None."""

    match = re.search(r'"num_total_variations"\s*:\s*(\d+)', html)

    if match:
        return int(match.group(1))

    return None


def build_rows_from_display(display_data, dimensions):
    """
    Build one row per ASIN from dimensionValuesDisplayData.

    The values are in the same order as the "dimensions" list,
    for example ["color_name", "size_name"].
    """

    rows = []
    seen_asins = set()

    for asin, values in display_data.items():

        asin = str(asin).strip().upper()

        if not asin or asin in seen_asins:
            continue

        seen_asins.add(asin)

        if not isinstance(values, list):
            values = []

        values = [str(value).strip() for value in values]

        labels = {}

        if dimensions and len(values) == len(dimensions):

            labels = dict(zip(dimensions, values))

        elif not dimensions and len(values) == 2:

            # No dimension names on the page: assume colour, then size.
            labels = {"color_name": values[0], "size_name": values[1]}

        rows.append({
            "asin": asin,
            "colour": labels.get("color_name") or labels.get("colour_name", ""),
            "size": labels.get("size_name", "")
        })

    return rows


def build_rows_from_index(dimensions, variation_values, index_map):
    """
    Fallback: join the index keys in dimensionToAsinMap (e.g. "4_15")
    to the label lists in variationValues (e.g. {"size_name": [...]}).
    """

    rows = []
    seen_asins = set()

    for raw_key, asin in index_map.items():

        asin = str(asin).strip().upper()

        if not asin or asin in seen_asins:
            continue

        seen_asins.add(asin)

        labels = {}

        for position, index_text in enumerate(str(raw_key).split("_")):

            if position >= len(dimensions):
                break

            name = dimensions[position]

            try:
                labels[name] = variation_values[name][int(index_text)]

            except (KeyError, IndexError, ValueError, TypeError):
                labels[name] = ""

        rows.append({
            "asin": asin,
            "colour": labels.get("color_name") or labels.get("colour_name", ""),
            "size": labels.get("size_name", "")
        })

    return rows


def extract_dimension_map(html):
    """
    Read the variation options from the page HTML.
    Returns (rows, status). The status says which method was used and
    whether the count matches Amazon's own total, so problems are
    visible in the app.
    """

    dimensions = read_json_value(html, "dimensions", list) or []

    display_data = read_json_value(html, "dimensionValuesDisplayData", dict)

    if display_data:

        rows = build_rows_from_display(display_data, dimensions)

        method = "display table"

    else:

        index_map = read_json_value(html, "dimensionToAsinMap", dict)

        variation_values = read_json_value(html, "variationValues", dict) or {}

        if not index_map:

            return [], "NOT FOUND - this page has no variation table"

        rows = build_rows_from_index(dimensions, variation_values, index_map)

        method = "index map"

    if not rows:

        return [], "NOT FOUND - the variation table was empty"

    rows.sort(key=lambda row: (row["size"], row["colour"]))

    labelled = sum(1 for row in rows if row["size"] or row["colour"])

    total = read_total_variations(html)

    count_note = ""

    if total and total != len(rows):

        count_note = f" (Amazon reports {total} variations)"

    if labelled == 0:

        return rows, f"PARTIAL - {len(rows)} ASINs found, labels missing ({method})"

    return rows, (
        f"FOUND - {len(rows)} ASINs with colour and size "
        f"({method}){count_note}"
    )


def load_variation_matrix(parent_url):
    """
    Open the product page with the verified UK postcode and read every
    colour and size combination. Nothing is read if the postcode is
    not confirmed, because prices would be wrong.
    """

    report = {
        "parent_url": parent_url,
        "checked_at": datetime.now().astimezone().isoformat(),
        "location_verified": False,
        "status": "NOT VERIFIED",
        "rows": []
    }

    with open_verified_amazon_page(parent_url) as (page, location):

        report["location_verified"] = bool(location.get("verified"))

        if not location.get("verified"):

            report["status"] = "LOCATION NOT VERIFIED"
            return report

        html = page.content()

    rows, status = extract_dimension_map(html)

    report["rows"] = rows
    report["status"] = status

    return report


def items_for_size(rows, size):
    """
    Build batch input for one size: every colour of that size.
    The shape matches parse_url_list(), so it goes straight into
    run_batch_audit().
    """

    if not size:
        return []

    return [
        {
            "url": "https://www.amazon.co.uk/dp/" + row["asin"],
            "asin": row["asin"]
        }
        for row in rows
        if row["size"] == size
    ]