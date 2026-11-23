"""
Build a specification template from a live listing family.

The Variation Matrix finds every colour x size of a product family. For
each size variation (e.g. "Single (135 x 200 cm)", "King ... - Pack of 2")
the bot reads the Product information of a few colours and builds ONE
template row from it:

- A value most colours agree on is used.
- If colours disagree (e.g. one colour shows another weight), the
  majority value is used and the difference is listed on the "Notes"
  sheet: the odd colour is probably the listing that needs correcting.
- Fields that differ for every listing by nature (ASIN, reviews, ranking,
  colour, model number, dates, prices) are left out.

The result is an Excel file with the sheet named as you choose (e.g.
"ES-DCS"), ready to review and upload on Specification Templates (or to
save straight away as a specification set).
"""

import re
from collections import Counter
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from modules.spec_checker import variant_tokens
from services.spec_service import DEFAULT_FIELDS, SIZE_COLUMN, TYPE_COLUMN
from services.variation_service import base_size


# Fields that are different for every listing, so they are not specifications.
SKIP_FIELDS = {
    "asin", "best sellers rank", "customer reviews", "date first available",
    "price", "colour", "color", "size", "size name", "model number",
    "item model number", "item part number", "part number", "ean", "upc",
    "global trade identification number", "gtin", "manufacturer reference",
    "is discontinued by manufacturer", "department", "batteries required",
    "batteries included", "units", "release date", "voltage", "wattage",
}

HEADER_FILL = PatternFill("solid", fgColor="068187")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _key(value):
    return _clean(value).lower()


def size_label(size_text):
    """
    The template Size for one variation, e.g.
      "King (220 x 230 cm) - Pack of 2" -> "King Pack of 2"
      "Double 4 Piece Set"              -> "Double 4 Piece"
      "Single (135 x 200 cm)"           -> "Single"
    """

    base = base_size(size_text)

    tokens = variant_tokens(size_text)

    label = base

    for token in sorted(tokens):
        if token.startswith("pieces:"):
            label += f" {token.split(':')[1]} Piece"

    for token in sorted(tokens):
        if token.startswith("pack:"):
            label += f" Pack of {token.split(':')[1]}"

    return label


def choose_items(rows, colours_per_size=3, sizes=None):
    """
    The products to read: for every size variation, the first
    `colours_per_size` colours. Returns batch items with colour and size.
    """

    chosen_sizes = set(sizes) if sizes is not None else None

    taken = {}
    items = []

    for row in rows:

        size = row.get("size") or ""

        if not size or (chosen_sizes is not None and size not in chosen_sizes):
            continue

        if taken.get(size, 0) >= colours_per_size:
            continue

        taken[size] = taken.get(size, 0) + 1

        items.append({
            "url": "https://www.amazon.co.uk/dp/" + row["asin"],
            "asin": row["asin"],
            "colour": row.get("colour", ""),
            "size": size,
        })

    return items


def build_template_rows(results, items, product_type):
    """
    One template row per size variation from the audit results.

    Returns (rows, notes, unread):
      rows:   [{"product_type", "size", "values": {field: value}}]
      notes:  [{"Size", "Field", "Value used", "Other values", "Read from"}]
      unread: [asin] products whose Product information could not be read
    """

    item_by_asin = {item["asin"]: item for item in items}

    details_by_size = {}
    unread = []

    for result in results:

        asin = result.get("asin", "")
        details = ((result.get("content") or {}).get("technical_details")) or {}

        if not details:
            unread.append(asin)
            continue

        size = item_by_asin.get(asin, {}).get("size", "")

        details_by_size.setdefault(size, []).append((asin, details))

    rows = []
    notes = []
    labels_used = {}

    for size, products in details_by_size.items():

        label = size_label(size)

        # Two variations with the same short name: keep the full name.
        if label in labels_used and labels_used[label] != size:
            label = size

        labels_used[label] = size

        fields = []

        for _, details in products:
            for field in details:
                if _key(field) not in SKIP_FIELDS and field not in fields:
                    fields.append(field)

        values = {}

        for field in fields:

            seen = [(asin, _clean(details[field])) for asin, details in products
                    if _clean(details.get(field))]

            if not seen:
                continue

            counts = Counter(_key(value) for _, value in seen)

            (top_key, top_count), = counts.most_common(1)

            tie = len(counts) > 1 and list(counts.values()).count(top_count) > 1

            if tie:
                notes.append({
                    "Size": label, "Field": field, "Value used": "(left empty: colours disagree)",
                    "Other values": "; ".join(f"{asin}: {value}" for asin, value in seen),
                    "Read from": ", ".join(asin for asin, _ in products),
                })
                continue

            value = next(value for _, value in seen if _key(value) == top_key)

            values[field] = value

            others = [(asin, other) for asin, other in seen if _key(other) != top_key]

            missing = [asin for asin, details in products if not _clean(details.get(field))]

            if others or missing:
                notes.append({
                    "Size": label, "Field": field, "Value used": value,
                    "Other values": "; ".join(
                        [f"{asin}: {other}" for asin, other in others]
                        + [f"{asin}: (not shown)" for asin in missing]
                    ),
                    "Read from": ", ".join(asin for asin, _ in products),
                })

        rows.append({"product_type": product_type, "size": label, "values": values})

    return rows, notes, unread


def _order_fields(rows):
    """Default template fields first (in their usual order), then the rest A-Z."""

    present = []

    for row in rows:
        for field in row["values"]:
            if field not in present:
                present.append(field)

    known = [field for field in DEFAULT_FIELDS if field in present]

    return known + sorted(field for field in present if field not in known)


def _write_table(sheet, headers, records):

    sheet.append(headers)

    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")

    for record in records:
        sheet.append(record)

    for column in sheet.columns:
        width = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(max(12, width + 2), 60)

    sheet.freeze_panes = "C2" if headers[:2] == [TYPE_COLUMN, SIZE_COLUMN] else "A2"


def build_template_workbook(rows, notes, sheet_name="ES-DCS"):
    """The Excel template (bytes): the specification sheet, Notes and Instructions."""

    sheet_name = re.sub(r"[\[\]:*?/\\]", "-", sheet_name or "ES-DCS")[:31]

    fields = _order_fields(rows)

    workbook = Workbook()

    sheet = workbook.active
    sheet.title = sheet_name

    _write_table(
        sheet,
        [TYPE_COLUMN, SIZE_COLUMN] + fields,
        [[row["product_type"], row["size"]] + [row["values"].get(field, "") for field in fields]
         for row in rows],
    )

    notes_sheet = workbook.create_sheet("Notes")

    note_headers = ["Size", "Field", "Value used", "Other values", "Read from"]

    _write_table(notes_sheet, note_headers, [[note[h] for h in note_headers] for note in notes])

    info = workbook.create_sheet("Instructions")

    for line in [
        "HOW THIS TEMPLATE WAS MADE",
        f"- The '{sheet_name}' sheet was built from the live Amazon UK Product information",
        "  of this listing family: one row per size variation.",
        "- When colours of the same size disagreed, the value most colours show was used,",
        "  and the difference is listed on the 'Notes' sheet. The odd colour is probably",
        "  the listing that needs correcting.",
        "",
        "BEFORE YOU UPLOAD",
        "- Check every value against your real product data: this template copies what",
        "  Amazon shows today, so a mistake already on Amazon would be copied too.",
        "- Fill any empty cells you know, and add columns such as 'Fitted Sheet",
        "  Dimensions' or 'Description contains' if you want them checked.",
        "- Then upload this file on Specification Templates.",
    ]:
        info.append([line])

    info.column_dimensions["A"].width = 95

    buffer = BytesIO()
    workbook.save(buffer)

    return buffer.getvalue()
