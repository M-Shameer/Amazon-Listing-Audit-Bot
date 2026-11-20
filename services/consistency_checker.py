"""
Cross-colour consistency checker.

Compares the audited products of one size with each other. Colour is
expected to differ, so it is never compared.

Missing values are grouped into one row per field, listing the ASINs
where the value was not read. A missing value is never treated as proof
that the field is empty.
"""

import re
from collections import Counter


# Fields that should match across colours of the same size.
MATCH_FIELDS = [
    "Seller",
    "Dispatches From",
    "Number of Pieces",
    "Number of Packs",
    "Pillowcase Width",
    "Pillowcase Length",
    "Item Dimensions",
    "Material Type",
    "Fabric Type",
    "Thread Count",
    "Closure Type",
    "Manufacturer Part Number",
]

# Price can legitimately differ by colour, so it is reported as a
# potential discrepancy rather than an inconsistency.
PRICE_FIELD = "Price"


def normalise(value):
    """Lower-case and collapse spaces so formatting differences are ignored."""

    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def collect_facts(result):
    """Gather the comparable fields for one audited product."""

    content = result.get("content") or {}
    buy_box = result.get("buy_box") or {}
    technical = content.get("technical_details") or {}

    facts = {
        "Seller": buy_box.get("seller", ""),
        "Dispatches From": buy_box.get("dispatches_from", ""),
        PRICE_FIELD: buy_box.get("price", ""),
    }

    for field in MATCH_FIELDS:
        if field not in facts:
            facts[field] = technical.get(field, "")

    return facts


def check_consistency(results):
    """
    Return a list of findings. Each finding is a dictionary with
    ASIN, Field, Classification and Detail.
    """

    usable = [
        result for result in results
        if (result.get("content") or {}).get("status") == "EXTRACTED"
    ]

    if len(usable) < 2:

        return [{
            "ASIN": "",
            "Field": "All",
            "Classification": "NOT VERIFIED",
            "Detail": "At least two products must be read before they can be compared."
        }]

    findings = []

    facts_by_asin = {
        result["asin"]: collect_facts(result)
        for result in usable
    }

    total = len(facts_by_asin)

    for field in MATCH_FIELDS + [PRICE_FIELD]:

        values = {
            asin: facts[field]
            for asin, facts in facts_by_asin.items()
        }

        # Group missing values into one row for the whole field.
        missing = [asin for asin, value in values.items() if not value]

        if len(missing) == total:

            findings.append({
                "ASIN": "All products",
                "Field": field,
                "Classification": "NOT VERIFIED",
                "Detail": (
                    "Not read from any product. This may be a page-reading "
                    "gap, not proof that the field is empty."
                )
            })

        elif missing:

            findings.append({
                "ASIN": ", ".join(missing),
                "Field": field,
                "Classification": "NOT VERIFIED",
                "Detail": (
                    f"Not read from {len(missing)} of {total} products. "
                    "This does not prove the field is empty."
                )
            })

        present = {asin: value for asin, value in values.items() if value}

        counts = Counter(normalise(value) for value in present.values())

        # Only compare when at least two different values exist.
        if len(counts) < 2:
            continue

        most_common_norm, _ = counts.most_common(1)[0]

        most_common_text = next(
            value for value in present.values()
            if normalise(value) == most_common_norm
        )

        for asin, value in present.items():

            if normalise(value) == most_common_norm:
                continue

            if field == PRICE_FIELD:

                classification = "Potential Discrepancy"
                note = " Price can differ by colour; confirm this is intended."

            else:

                classification = "Inconsistency - verify"
                note = ""

            findings.append({
                "ASIN": asin,
                "Field": field,
                "Classification": classification,
                "Detail": (
                    f"Shows '{value}'. Most products show "
                    f"'{most_common_text}'.{note}"
                )
            })

    # Repeated bullet points inside one listing are a real listing issue.
    for result in usable:

        bullets = (result.get("content") or {}).get("bullets") or []

        counts = Counter(normalise(bullet) for bullet in bullets)

        for text, count in counts.items():

            if count > 1:

                findings.append({
                    "ASIN": result["asin"],
                    "Field": "Bullet points",
                    "Classification": "Confirmed Error",
                    "Detail": f"The same bullet point appears {count} times."
                })

    return findings