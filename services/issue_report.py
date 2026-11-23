"""
Issue report (pure functions, no browser, no Streamlit).

Turns full audit results into two clear tables:

1. build_issue_rows(results)
   One row per problem: "ASIN B0XXXXXXXX has THIS issue".
   Columns: ASIN, Severity, Area, Issue, Amazon Shows, Should Be, What To Do.

2. build_product_scorecard(results)
   One row per product: result, issue counts by severity,
   Featured Offer, and how long the check took.

Severity order: High, Medium, Low, Check, Advice.
"Check" means the bot could not confirm something; a person should look.
"""

SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2, "Check": 3, "Advice": 4}

ISSUE_COLUMNS = [
    "ASIN", "Severity", "Area", "Issue", "Amazon Shows", "Should Be", "What To Do"
]

# Featured Offer verdicts that are problems.
FEATURED_OFFER_PROBLEMS = {
    "HELD BY ANOTHER SELLER": (
        "High", "Another seller holds the Featured Offer (Buy Box)",
        "Check price, stock and delivery speed against the other seller."
    ),
    "NO FEATURED OFFER": (
        "High", "No Featured Offer (no Buy Box)",
        "Check stock, price and account health in Seller Central."
    ),
    "NOT VERIFIED": (
        "Check", "Featured Offer could not be read",
        "Open the product page and check the Buy Box by eye."
    ),
    "BLOCKED": (
        "Check", "Amazon showed a security check",
        "Complete the check in the bot's Chrome window, then recheck."
    ),
}


# Products that were not checked at all get ONE short row, not a row
# per failed step (the reason is the same for every step).
NOT_CHECKED = {
    "LOCATION NOT VERIFIED": (
        "Not checked: Amazon was not using your postcode",
        "Click 'Verify Location in Chrome' on the Delivery Location page, then audit again."
    ),
    "BLOCKED BY AMAZON": (
        "Not checked: Amazon showed a security check",
        "Turn off 'Run Chrome in the background', run again and complete the check in the window."
    ),
    "FAILED": (
        "Not checked: the page could not be opened",
        "Check the link or ASIN, then audit it again."
    ),
}


def _row(asin, severity, area, issue, shows="", should="", action=""):

    return {
        "ASIN": asin,
        "Severity": severity,
        "Area": area,
        "Issue": issue,
        "Amazon Shows": str(shows or ""),
        "Should Be": str(should or ""),
        "What To Do": action,
    }


def issues_for_product(result):
    """Every problem found for one product, as table rows."""

    asin = result.get("asin", "")
    rows = []

    buy_box = result.get("buy_box") or {}
    location = buy_box.get("location") or {}

    status = result.get("overall_status")

    if status in NOT_CHECKED:
        issue, action = NOT_CHECKED[status]
        shows = location.get("amazon_header", "") if status == "LOCATION NOT VERIFIED" else ""
        return [_row(asin, "Check", "Not checked", issue, shows,
                     location.get("saved_postcode", ""), action)]

    # 1. Delivery location
    if buy_box and not location.get("verified") and not location.get("security_challenge"):
        rows.append(_row(
            asin, "Check", "Delivery location", "Amazon was not using your saved postcode",
            location.get("amazon_header") or "(nothing)", location.get("saved_postcode"),
            "Verify the location, then recheck this product."
        ))

    # 2. Featured Offer
    verdict = buy_box.get("featured_offer_verdict")

    if verdict in FEATURED_OFFER_PROBLEMS:
        severity, issue, action = FEATURED_OFFER_PROBLEMS[verdict]
        rows.append(_row(
            asin, severity, "Featured Offer", issue,
            buy_box.get("seller") or "Not verified",
            buy_box.get("expected_seller") or "Your seller", action
        ))

    # 3. Listing quality (title, bullets, description, images)
    for finding in result.get("quality") or []:
        rows.append(_row(
            asin, finding.get("severity", "Low"), finding.get("area", ""),
            finding.get("rule", ""), finding.get("found"), finding.get("expected"),
            finding.get("action", "")
        ))

    # 3b. Text inside the images (OCR)
    for finding in (result.get("image_text") or {}).get("findings") or []:
        rows.append(_row(
            asin, finding.get("severity", "Low"), finding.get("area", ""),
            finding.get("rule", ""), finding.get("found"), finding.get("expected"),
            finding.get("action", "")
        ))

    # 3c. Colour name and videos vs listing images
    for finding in (result.get("visual") or {}).get("findings") or []:
        rows.append(_row(
            asin, finding.get("severity", "Check"), finding.get("area", ""),
            finding.get("rule", ""), finding.get("found"), finding.get("expected"),
            finding.get("action", "")
        ))

    # 4. Spelling (British English rules)
    for issue in (result.get("spelling") or {}).get("issues") or []:
        rows.append(_row(
            asin, issue.get("severity") or "Low", issue.get("location", "Listing text"),
            "Spelling: " + str(issue.get("detected_term", "")),
            issue.get("detected_term"), issue.get("correct_term"),
            "Correct the spelling in Seller Central."
        ))

    # 5. Specification mismatches
    for issue in (result.get("spec_check") or {}).get("issues") or []:
        rows.append(_row(
            asin, "High", issue.get("location", "Product information"),
            "Does not match your specification",
            issue.get("detected_term"), issue.get("correct_term"),
            "Correct the attribute in Seller Central (or the template)."
        ))

    # 6. A+, Brand Story, images displayed; A+ design match
    for finding in result.get("content_findings") or []:
        missing = "NOT" in str(finding.get("Status", "")).upper()
        rows.append(_row(
            asin, "High" if missing else "Medium", finding.get("Item", "Content"),
            "Missing" if missing else str(finding.get("Status", "")).capitalize(),
            "Not shown" if missing else "",
            ("Shown, like " + finding["Example"]) if finding.get("Example") else "",
            finding.get("Detail", "")
        ))

    # 7. Things the bot could not read
    for gap in (result.get("spelling") or {}).get("data_gaps") or []:
        rows.append(_row(
            asin, "Check", str(gap.get("field", "")).capitalize() or "Listing",
            "Not verified", "", "", gap.get("reason", "")
        ))

    # 8. Problems during the check
    for message in result.get("errors") or []:
        rows.append(_row(
            asin, "Check", "Audit run", "Problem during the check", "", "", message
        ))

    return rows


def build_issue_rows(results):
    """All problems of a batch, most serious first, grouped by ASIN."""

    rows = []

    for result in results:
        rows.extend(issues_for_product(result))

    asin_order = {}

    for result in results:
        asin_order.setdefault(result.get("asin", ""), len(asin_order))

    rows.sort(key=lambda row: (
        SEVERITY_ORDER.get(row["Severity"], 9),
        asin_order.get(row["ASIN"], 0)
    ))

    return rows


def build_product_scorecard(results):
    """One row per product with a plain result and issue counts."""

    card = []

    for result in results:

        rows = issues_for_product(result)

        counts = {name: 0 for name in SEVERITY_ORDER}

        for row in rows:
            counts[row["Severity"]] = counts.get(row["Severity"], 0) + 1

        problems = counts["High"] + counts["Medium"] + counts["Low"]

        if result.get("overall_status") in ("FAILED", "BLOCKED BY AMAZON", "LOCATION NOT VERIFIED"):
            verdict = "⚠️ Not checked"
        elif counts["High"]:
            verdict = "❌ Fix now"
        elif problems:
            verdict = "🟠 Improve"
        elif counts["Check"]:
            verdict = "⚠️ Check by eye"
        else:
            verdict = "✅ No issues"

        buy_box = result.get("buy_box") or {}

        if verdict == "⚠️ Not checked":
            problems_text = rows[:1]
        else:
            # Only real errors (the Buy Box has its own column).
            problems_text = [
                row for row in rows
                if row["Severity"] in ("High", "Medium", "Low") and row["Area"] != "Featured Offer"
            ]

        problems_text.sort(key=lambda row: SEVERITY_ORDER.get(row["Severity"], 9))

        card.append({
            "ASIN": result.get("asin", ""),
            "Result": verdict,
            "Buy Box": buy_box_text(buy_box),
            "What's Wrong": "\n".join(
                "• " + _short_issue(row) for row in problems_text
            ) or "Nothing found",
            "High": counts["High"],
            "Medium": counts["Medium"],
            "Low": counts["Low"],
            "Check": counts["Check"],
            "Advice": counts["Advice"],
            "Seconds": result.get("seconds_per_listing") or result.get("seconds", ""),
            "Title": ((result.get("content") or {}).get("title") or "")[:70],
        })

    return card


# Issue names that add nothing once the values are shown.
_GENERIC = ("Does not match your specification", "Missing")


def _short_value(value, limit=45):
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[:limit - 1] + "…"


def _short_issue(row):
    """
    One issue as short text: what is wrong and what it should be.
      "Number of Pieces: 2 → should be 4"
      "A+ content (EBC): Not shown → should be Shown, like B0..."
      "Title: Special characters not allowed (!)"
    """

    area = str(row.get("Area") or "")
    for prefix in ("Product information: ", "Listing text: "):
        if area.startswith(prefix):
            area = area[len(prefix):]

    issue = str(row.get("Issue") or "")
    if issue.startswith("Spelling: "):
        issue = "Spelling"

    shows = _short_value(row.get("Amazon Shows"))
    should = _short_value(row.get("Should Be"))

    if should.lower() in ("none", "nothing", "(none)"):
        should = "removed"

    if shows and should and (issue in _GENERIC or issue == "Spelling"):
        label = area if issue in _GENERIC else f"{area} spelling"
        return f"{label}: {shows} → should be {should}"

    text = issue if area and area.lower() in issue.lower() else f"{area}: {issue}" if area else issue

    if shows and should:
        text += f" ({shows} → should be {should})"
    elif shows:
        text += f" ({shows})"

    return text


def buy_box_text(buy_box):
    """The Buy Box column: does this ASIN have the Buy Box, and who holds it."""

    verdict = (buy_box or {}).get("featured_offer_verdict") or ""
    seller = (buy_box or {}).get("seller") or ""

    if verdict == "HELD BY YOUR SELLER":
        return "✅ Yes (yours)"
    if verdict == "HELD BY ANOTHER SELLER":
        return "❌ Lost to " + (seller or "another seller")
    if verdict == "HELD":
        return "✅ Yes" + (f" ({seller})" if seller else "")
    if verdict == "NO FEATURED OFFER":
        return "❌ No Buy Box"
    return "⚠️ Not verified"


def rows_to_tsv(rows, columns=None):
    """Rows as tab-separated text: pastes straight into Excel columns."""

    if not rows:
        return ""

    columns = columns or list(rows[0].keys())

    def cell(value):
        return str(value if value is not None else "").replace("\t", " ").replace("\n", " ")

    lines = ["\t".join(columns)]
    lines += ["\t".join(cell(row.get(column, "")) for column in columns) for row in rows]

    return "\n".join(lines)


def not_checked_summary(results):
    """{reason: [asins]} for products that could not be checked at all."""

    summary = {}

    for result in results:
        status = result.get("overall_status")
        if status in NOT_CHECKED:
            summary.setdefault(status, []).append(result.get("asin", ""))

    return summary


def batch_totals(results):
    """Headline numbers for the result page."""

    card = build_product_scorecard(results)

    seconds = [row["Seconds"] for row in card if isinstance(row["Seconds"], (int, float))]

    per_listing = next((r.get("seconds_per_listing") for r in results if r.get("seconds_per_listing")), None)
    if per_listing:
        seconds = [per_listing]

    return {
        "products": len(card),
        "fix_now": sum(1 for row in card if row["Result"].startswith("❌")),
        "improve": sum(1 for row in card if row["Result"].startswith("🟠")),
        "clean": sum(1 for row in card if row["Result"].startswith("✅")),
        "issues": sum(row["High"] + row["Medium"] + row["Low"] for row in card),
        "buy_box_lost": sum(1 for row in card if row["Buy Box"].startswith("❌")),
        "total_seconds": next((r.get("batch_seconds") for r in results if r.get("batch_seconds")), None),
        "average_seconds": round(sum(seconds) / len(seconds), 1) if seconds else None,
    }
