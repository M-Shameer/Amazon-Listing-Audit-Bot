"""
Excel report generator.

Builds .xlsx workbooks in memory with openpyxl. The website offers
them as downloads, so nothing is written to disk unless you save it.
"""

import re
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from services.issue_report import ISSUE_COLUMNS, build_issue_rows, build_product_scorecard


HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")

# Colour of the Severity cell in the All Issues sheet.
SEVERITY_FILLS = {
    "High": PatternFill("solid", fgColor="F8C9D4"),
    "Medium": PatternFill("solid", fgColor="FFE2C2"),
    "Low": PatternFill("solid", fgColor="FFF4C2"),
    "Check": PatternFill("solid", fgColor="D9E3EC"),
    "Advice": PatternFill("solid", fgColor="D6F1EF"),
}

# Characters Excel cannot store. Removing them prevents file errors.
ILLEGAL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_value(value):
    """Turn any value into text that Excel accepts."""

    if value is None:
        return ""

    return ILLEGAL_CHARS.sub("", str(value))


def write_sheet(workbook, title, headers, rows):
    """Write one sheet with a coloured header, filters and sized columns."""

    sheet = workbook.create_sheet(title=title[:31])

    sheet.append(headers)

    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="top")

    severity_column = headers.index("Severity") + 1 if "Severity" in headers else None

    for row in rows:
        sheet.append([clean_value(row.get(header, "")) for header in headers])

        if severity_column:
            fill = SEVERITY_FILLS.get(row.get("Severity"))
            if fill:
                sheet.cell(row=sheet.max_row, column=severity_column).fill = fill

    sheet.freeze_panes = "A2"

    if rows:
        sheet.auto_filter.ref = sheet.dimensions

    # Column width: the longest value in each column, capped at 60.
    for index, header in enumerate(headers, start=1):

        longest = max(
            [len(str(header))]
            + [len(clean_value(row.get(header, ""))) for row in rows]
        )

        sheet.column_dimensions[
            sheet.cell(row=1, column=index).column_letter
        ].width = min(longest + 2, 60)

    return sheet


def build_workbook(sheets):
    """
    sheets is a list of (title, headers, rows) tuples.
    Returns the workbook as bytes, ready for st.download_button.
    """

    workbook = Workbook()

    # Remove the default empty sheet created by openpyxl.
    workbook.remove(workbook.active)

    for title, headers, rows in sheets:
        write_sheet(workbook, title, headers, rows)

    buffer = BytesIO()
    workbook.save(buffer)

    return buffer.getvalue()


def build_batch_workbook(summary_rows, results):
    """
    Sheets for a batch audit:
    - All Issues: every problem, one row each ("ASIN X has this issue").
    - Product Results: one row per product with issue counts.
    - Summary: one row per product (all details).
    - Issues: every spelling and rule finding, with original and suggested text.
    - Not Verified: data gaps, Featured Offer warnings and run problems.
    - Spec Check: only when a specification set was chosen.
    - Content Display: listing images, A+ content and Brand Story.
    - A+ Design Check: only when the design check was switched on.
    """

    summary_headers = list(summary_rows[0].keys()) if summary_rows else []

    issue_headers = [
        "ASIN", "Issue ID", "Location", "Found", "Suggested",
        "Classification", "Reason", "Original Text", "Suggested Text"
    ]

    gap_headers = ["ASIN", "Item", "Status", "Reason"]

    spec_headers = [
        "ASIN", "Specification Set", "Product Type", "Amazon Size",
        "Template Size", "Field", "Your Specification", "Amazon Shows",
        "Result", "Note"
    ]

    content_headers = [
        "ASIN", "Listing Images", "Listing Image Count", "A+ Content",
        "A+ Modules", "A+ Images", "Brand Story", "Brand Story Images",
        "A+ Design", "Main Image URL"
    ]

    design_headers = [
        "ASIN", "A+ Image", "Score", "Verdict",
        "A+ Image URL", "Best Matching Listing Image"
    ]

    issue_rows = []
    gap_rows = []
    spec_rows = []
    content_rows = []
    design_rows = []

    for result in results:

        asin = result.get("asin", "")

        spelling = result.get("spelling") or {}

        for issue in spelling.get("issues", []):

            issue_rows.append({
                "ASIN": asin,
                "Issue ID": issue.get("issue_id"),
                "Location": issue.get("location"),
                "Found": issue.get("detected_term"),
                "Suggested": issue.get("correct_term"),
                "Classification": issue.get("classification"),
                "Reason": issue.get("reason"),
                "Original Text": issue.get("original_text"),
                "Suggested Text": issue.get("suggested_correction")
            })

        for gap in spelling.get("data_gaps", []):

            gap_rows.append({
                "ASIN": asin,
                "Item": gap.get("field"),
                "Status": gap.get("status"),
                "Reason": gap.get("reason")
            })

        buy_box = result.get("buy_box") or {}

        # Only list the Featured Offer here when it is not a clear result.
        verdict = buy_box.get("featured_offer_verdict", "")

        if buy_box and verdict not in ("HELD BY YOUR SELLER", "HELD"):

            gap_rows.append({
                "ASIN": asin,
                "Item": "Featured Offer",
                "Status": verdict or "NOT VERIFIED",
                "Reason": buy_box.get("featured_offer_status", "")
            })

        spec_check = result.get("spec_check") or {}

        if spec_check:

            base = {
                "ASIN": asin,
                "Specification Set": spec_check.get("set_name"),
                "Product Type": spec_check.get("product_type"),
                "Amazon Size": spec_check.get("amazon_size"),
                "Template Size": spec_check.get("template_size"),
            }

            if spec_check.get("rows"):
                for row in spec_check["rows"]:
                    spec_rows.append({**base, **row})
            else:
                spec_rows.append({**base, "Result": spec_check.get("status")})

        display = result.get("content_display") or {}
        design = result.get("design_check") or {}

        if display:

            listing = display.get("listing_images") or {}
            aplus = display.get("aplus") or {}
            brand = display.get("brand_story") or {}

            content_rows.append({
                "ASIN": asin,
                "Listing Images": listing.get("status"),
                "Listing Image Count": listing.get("count"),
                "A+ Content": aplus.get("status"),
                "A+ Modules": aplus.get("modules"),
                "A+ Images": aplus.get("image_count"),
                "Brand Story": brand.get("status"),
                "Brand Story Images": brand.get("image_count"),
                "A+ Design": design.get("overall") or "Not checked",
                "Main Image URL": listing.get("main_image"),
            })

        for row in design.get("rows", []):
            design_rows.append({"ASIN": asin, **row})

        for finding in result.get("content_findings", []):
            gap_rows.append({
                "ASIN": asin,
                "Item": finding.get("Item"),
                "Status": finding.get("Status"),
                "Reason": finding.get("Detail")
            })

        for message in result.get("errors", []):

            gap_rows.append({
                "ASIN": asin,
                "Item": "Run problem",
                "Status": "ERROR",
                "Reason": message
            })

    all_issues = build_issue_rows(results)
    scorecard = build_product_scorecard(results)

    sheets = [
        ("Product Results", list(scorecard[0].keys()) if scorecard else [], scorecard),
        ("All Issues", ISSUE_COLUMNS, all_issues),
        ("Summary", summary_headers, summary_rows),
        ("Spelling Issues", issue_headers, issue_rows),
        ("Not Verified", gap_headers, gap_rows)
    ]

    if spec_rows:
        sheets.append(("Spec Check", spec_headers, spec_rows))

    if content_rows:
        sheets.append(("Content Display", content_headers, content_rows))

    if design_rows:
        sheets.append(("A+ Design Check", design_headers, design_rows))

    return build_workbook(sheets)


def build_matrix_workbook(rows):
    """One sheet listing every colour and size with its ASIN."""

    headers = ["ASIN", "Colour", "Size", "Link"]

    link_rows = [
        {
            "ASIN": row["asin"],
            "Colour": row["colour"],
            "Size": row["size"],
            "Link": "https://www.amazon.co.uk/dp/" + row["asin"]
        }
        for row in rows
    ]

    return build_workbook([("Variation Matrix", headers, link_rows)])