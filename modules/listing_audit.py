
import re
import json


def correct_microfiber_spelling(text):
    """
    Replace American spelling 'Microfiber'
    with British spelling 'Microfibre'.
    Preserve the original capitalization.
    """

    def replace_word(match):
        word = match.group(0)

        if word.isupper():
            return "MICROFIBRE"

        if word[0].isupper():
            return "Microfibre"

        return "microfibre"

    corrected_text = re.sub(
        r"\bmicrofiber\b",
        replace_word,
        text,
        flags=re.IGNORECASE
    )

    return corrected_text


def inspect_text(text, location, issues):
    """
    Inspect one listing text field for spelling errors.
    """

    if not isinstance(text, str) or not text.strip():
        return

    matches = list(
        re.finditer(
            r"\bmicrofiber\b",
            text,
            flags=re.IGNORECASE
        )
    )

    if not matches:
        return

    corrected_text = correct_microfiber_spelling(text)

    issue = {
        "issue_id": f"UKSPELL-{len(issues) + 1:03d}",
        "category": "British English Spelling",
        "location": location,
        "detected_term": "Microfiber",
        "correct_term": "Microfibre",
        "occurrences": len(matches),
        "original_text": text,
        "suggested_correction": corrected_text,
        "severity": "Low",
        "classification": "Confirmed Error",
        "reason": (
            "The project requires British English spelling. "
            "'Microfiber' should be written as 'Microfibre'."
        )
    }

    issues.append(issue)


def audit_listing(product_data):
    """
    Run rule-based checks on extracted Amazon product information.

    Returns confirmed errors, observations and data gaps separately.
    """

    issues = []
    observations = []
    data_gaps = []

    # 1. Inspect product title
    inspect_text(
        product_data.get("title", ""),
        "Product Title",
        issues
    )

    # 2. Inspect every bullet point
    bullets = product_data.get("bullets", [])

    if isinstance(bullets, list):
        for index, bullet in enumerate(bullets, start=1):
            inspect_text(
                bullet,
                f"Bullet Point {index}",
                issues
            )

    # 3. Inspect product description
    description = product_data.get("description", "")

    if description:
        inspect_text(
            description,
            "Product Description",
            issues
        )
    else:
        data_gaps.append({
            "field": "Product Description",
            "status": "NOT VERIFIED",
            "reason": (
                "No description text was extracted. "
                "This does not prove that the Amazon listing "
                "has no description."
            )
        })

    # 4. Inspect technical details, when available
    technical_details = product_data.get(
        "technical_details", {}
    )

    if isinstance(technical_details, dict):
        for name, value in technical_details.items():
            inspect_text(
                str(value),
                f"Technical Detail: {name}",
                issues
            )

    # 5. Inspect image text, when available
    image_text = product_data.get("image_text", [])

    if isinstance(image_text, list):
        for index, text in enumerate(image_text, start=1):
            inspect_text(
                text,
                f"Image Text {index}",
                issues
            )

    # 6. Record delivery restrictions separately
    availability = product_data.get("availability", "")

    if (
        isinstance(availability, str)
        and "cannot be dispatched" in availability.lower()
    ):
        observations.append({
            "category": "Delivery Availability",
            "classification": "NOT VERIFIED",
            "message": availability,
            "reason": (
                "Delivery depends on the selected location. "
                "We need to verify the listing using the "
                "intended UK delivery postcode."
            )
        })

    # 7. Prepare audit summary
    summary = {
        "asin": product_data.get("asin", ""),
        "confirmed_errors": len(issues),
        "observations": len(observations),
        "data_gaps": len(data_gaps),
        "audit_result": (
            "ISSUES FOUND"
            if issues
            else "NO RULE-BASED ISSUES FOUND"
        )
    }

    return {
        "summary": summary,
        "issues": issues,
        "observations": observations,
        "data_gaps": data_gaps
    }


# -------------------------------------------------
# TEST THE AUDIT ENGINE
# -------------------------------------------------

if __name__ == "__main__":

    sample_product = {
        "asin": "B0AAAAAA01",

        "title": (
            "Brightbed Double Duvet Set Premium "
            "Brushed Microfiber Duvet Cover"
        ),

        "bullets": [
            "Made with premium microfiber material.",
            "Soft and comfortable bedding."
        ],

        "description": "",

        "availability": (
            "This item cannot be dispatched to your "
            "selected delivery location. Please choose "
            "a different delivery location."
        )
    }

    audit_result = audit_listing(sample_product)

    print("\n========== LISTING AUDIT REPORT ==========")

    print(
        json.dumps(
            audit_result,
            indent=4,
            ensure_ascii=False
        )
    )

    print("\n===========================================")
