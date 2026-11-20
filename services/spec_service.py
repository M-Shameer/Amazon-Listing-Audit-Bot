"""
Specification template service.

1. build_blank_template()  -> an Excel file you download and fill in
2. parse_template(bytes)   -> reads your filled file and checks it
3. save / list / load / delete specification sets in the database

A "specification set" is one uploaded file, saved under a name you
choose (for example "Brightbed Bedding 2026"). It can hold several
product types (Duvet Cover Set, Fitted Sheet ...) and several sizes.
"""

import json
import re
from datetime import datetime
from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from database.db import get_connection


SHEET_NAME = "Specifications"

TYPE_COLUMN = "Product Type"
SIZE_COLUMN = "Size"

# Default field columns. Each name must be written exactly as Amazon
# writes it in the "Product information" table. You may add more
# columns in Excel; every extra column is checked the same way.
DEFAULT_FIELDS = [
    "Number of Pieces",
    "Included Components",
    "Item Dimensions",
    "Item Weight",
    "Thread Count",
    "Material Type",
    "Fabric Type",
    "Pillowcase Width",
    "Pillowcase Length",
    "Pillowcase Quantity",
    "Fitted Sheet Dimensions",
    "Fitted Sheet Pocket Depth",
    "Closure Type",
    "Product Care Instructions",
    "Brand Name",
    "Manufacturer",
    "Country Of Origin",
]

DEFAULT_PRODUCT_TYPES = ["Duvet Cover Set", "Fitted Sheet"]

DEFAULT_SIZES = ["Single", "Double", "King", "Super King"]

# One filled example row, taken from a real public listing, shown on
# the Instructions sheet only (never imported).
EXAMPLE_ROW = {
    TYPE_COLUMN: "Duvet Cover Set",
    SIZE_COLUMN: "Double",
    "Number of Pieces": "3",
    "Included Components": "Duvet Cover Set (1 x Duvet Cover + 2 x Pillowcases)",
    "Item Dimensions": "200 x 200 cm",
    "Item Weight": "",
    "Thread Count": "200",
    "Material Type": "Microfibre",
    "Fabric Type": "100% Microfibre",
    "Pillowcase Width": "50 cm",
    "Pillowcase Length": "75 cm",
    "Pillowcase Quantity": "2",
    "Closure Type": "Zipper",
}

HEADER_FILL = PatternFill("solid", fgColor="4546C8")
KEY_FILL = PatternFill("solid", fgColor="16A6C9")
HEADER_FONT = Font(bold=True, color="FFFFFF")


# =========================================
# 1. BLANK TEMPLATE
# =========================================

def build_blank_template():
    """Return a ready-to-fill Excel template as bytes."""

    workbook = Workbook()

    # ---- Sheet 1: Specifications (the sheet you fill in) ----
    sheet = workbook.active
    sheet.title = SHEET_NAME

    headers = [TYPE_COLUMN, SIZE_COLUMN] + DEFAULT_FIELDS

    sheet.append(headers)

    for product_type in DEFAULT_PRODUCT_TYPES:
        for size in DEFAULT_SIZES:
            sheet.append([product_type, size] + [""] * len(DEFAULT_FIELDS))

    for index, cell in enumerate(sheet[1], start=1):
        cell.fill = KEY_FILL if index <= 2 else HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        sheet.column_dimensions[cell.column_letter].width = 22 if index > 2 else 18

    sheet.row_dimensions[1].height = 34
    sheet.freeze_panes = "C2"

    # Treat every cell as text, so Excel does not change "1/2" into a date.
    for row in sheet.iter_rows(min_row=2, max_row=200, max_col=len(headers)):
        for cell in row:
            cell.number_format = "@"

    # Drop-down list for Product Type (you can still type a new one).
    validation = DataValidation(
        type="list",
        formula1='"' + ",".join(DEFAULT_PRODUCT_TYPES) + '"',
        allow_blank=True,
        showErrorMessage=False
    )
    sheet.add_data_validation(validation)
    validation.add("A2:A200")

    # ---- Sheet 2: Instructions ----
    guide = workbook.create_sheet("Instructions")

    lines = [
        "HOW TO FILL THIS TEMPLATE",
        "",
        "1. Fill the 'Specifications' sheet: one row per product type and size.",
        "2. 'Product Type' and 'Size' are required on every row you fill.",
        "3. 'Size' names the variation: a size, and optionally the number of",
        "   pieces and the pack, e.g. 'Double', 'Double 4 Piece', 'King Pack of 2',",
        "   'Super King 4 Piece Pack of 2'. ('SKing' and 'S King' also mean Super King.)",
        "   The bot reads Amazon's size, style, pieces and pack, and uses the MOST",
        "   specific row that fits: 'Double Pack of 2' beats 'Double'.",
        "   'King' never matches 'Super King'. One row per variation.",
        "",
        "EXTRA COLUMNS",
        "- You may add any column. Its name must be the field name exactly as",
        "  Amazon shows it in Product information (e.g. 'Pattern', 'Style Name',",
        "  'Colour'). The value is compared with the same spelling (capital",
        "  letters and spaces do not matter).",
        "- Text columns search the listing itself:",
        "    'Title contains', 'Bullets contain', 'Description contains',",
        "    'Listing contains' (title + bullets + description).",
        "  Put the exact words that must appear, e.g. '100% Egyptian Cotton'.",
        "  Several phrases: separate them with ;  e.g. 'Oeko-Tex; 400 Thread Count'.",
        "",
        "PARTS OF A SET (fitted sheet in a 3 or 4 piece set, pillowcases ...)",
        "- Columns such as 'Fitted Sheet Dimensions' (e.g. '150 x 200 cm') and",
        "  'Fitted Sheet Pocket Depth' (e.g. '35 cm') are compared with Amazon's",
        "  field of the same name. If Amazon has no such field, the bot reads the",
        "  title, bullet points and description near the words 'fitted sheet' or",
        "  'pocket' and compares the measurement written there.",
        "",
        "SEVERAL SHEETS",
        "- Every sheet whose first row has 'Product Type' and 'Size' is read, e.g.",
        "  one sheet for Fitted Sheets and one for Duvet Cover Sets.",
        "",
        "UNITS",
        "- Always write the unit: '0.53 kg' or '530 g' (NOT '0.53G', which means",
        "  0.53 grams). 'cm', 'mm', 'm', 'in', 'g', 'kg', 'oz' and 'lb' are understood.",
        "- Item Dimensions may include the size name: 'King (220 x 230 cm)'.",
        "  The order of the numbers and an extra depth on Amazon are allowed.",
        "4. Leave a cell EMPTY to skip that check.",
        "5. Column names must match Amazon's 'Product information' labels exactly.",
        "   You may add new columns (e.g. 'Pocket Depth') using Amazon's label.",
        "6. Units are understood: '1.2 kg' equals '1200 grams', '200 x 200 cm'",
        "   equals '200 x 200 centimetres'.",
        "7. Add more rows for other product types or sizes as needed.",
        "8. Save the file, then upload it on the 'Specification Templates' page.",
        "",
        "EXAMPLE ROW (this row is NOT imported):",
    ]

    for line in lines:
        guide.append([line])

    guide["A1"].font = Font(bold=True, size=14, color="4546C8")
    guide.column_dimensions["A"].width = 80

    guide.append([])
    guide.append(list(EXAMPLE_ROW.keys()))
    guide.append(list(EXAMPLE_ROW.values()))

    for cell in guide[guide.max_row - 1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT

    buffer = BytesIO()
    workbook.save(buffer)

    return buffer.getvalue()


# =========================================
# 2. READ AN UPLOADED TEMPLATE
# =========================================

def cell_text(value):
    """Turn an Excel cell into clean text. 200.0 becomes '200'."""

    if value is None:
        return ""

    if isinstance(value, float) and value.is_integer():
        value = int(value)

    return " ".join(str(value).split())


def _weight_warning(product_type, size, field, text):
    """
    A weight written in grams that is far too light for bedding (e.g.
    "0.53G" = 0.53 grams) is almost certainly meant in kilograms.
    """

    if "weight" not in field.lower():
        return ""

    match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(g|gm|gms|gram|grams)\s*", text, re.IGNORECASE)

    if match and float(match.group(1).replace(",", ".")) < 10:
        return (
            f"{product_type} / {size}: {field} '{text}' means {match.group(1)} GRAMS. "
            f"If you mean kilograms, write '{match.group(1)} kg'."
        )

    return ""


def _read_sheet(sheet, result, rows_by_key, weight_warnings):
    """Read one sheet that has Product Type and Size columns. Returns True if it had them."""

    all_rows = list(sheet.iter_rows(values_only=True))

    if not all_rows:
        return False

    headers = [cell_text(value) for value in all_rows[0]]

    lower_headers = [header.lower() for header in headers]

    if TYPE_COLUMN.lower() not in lower_headers or SIZE_COLUMN.lower() not in lower_headers:
        return False

    type_index = lower_headers.index(TYPE_COLUMN.lower())
    size_index = lower_headers.index(SIZE_COLUMN.lower())

    field_indexes = [
        (index, header)
        for index, header in enumerate(headers)
        if header and index not in (type_index, size_index)
    ]

    for _, header in field_indexes:
        if header not in result["fields"]:
            result["fields"].append(header)

    seen_here = set()

    for excel_row, values in enumerate(all_rows[1:], start=2):

        values = list(values) + [None] * (len(headers) - len(values))

        product_type = cell_text(values[type_index])
        size = cell_text(values[size_index])

        field_values = {
            header: cell_text(values[index])
            for index, header in field_indexes
        }

        has_data = any(field_values.values())

        if not product_type and not size and not has_data:
            continue  # completely empty row

        where = f"Sheet '{sheet.title}', row {excel_row}"

        if not product_type or not size:
            if has_data:
                result["warnings"].append(
                    f"{where} skipped: '{TYPE_COLUMN}' and '{SIZE_COLUMN}' are required."
                )
            continue

        key = (product_type.lower(), size.lower())

        if key in seen_here:
            result["warnings"].append(
                f"{where} skipped: {product_type} / {size} appears twice on this sheet "
                "(the first row was kept)."
            )
            continue

        seen_here.add(key)

        for field, text in field_values.items():
            warning = _weight_warning(product_type, size, field, text)
            if warning:
                weight_warnings.append(warning)

        row = {"product_type": product_type, "size": size, "values": field_values}

        existing = rows_by_key.get(key)

        if existing is None:
            rows_by_key[key] = row
            result["rows"].append(row)

        elif not any(existing["values"].values()) and has_data:
            # Empty on an earlier sheet, filled here: use the filled row.
            existing["values"] = field_values

        elif has_data:
            result["warnings"].append(
                f"{where} skipped: {product_type} / {size} is already filled on another sheet."
            )

    return True


def parse_template(file_bytes):
    """
    Read a filled template.

    EVERY sheet whose first row has 'Product Type' and 'Size' columns is
    read (e.g. one sheet for fitted sheets and one for duvet cover sets).
    Other sheets (lists of links, instructions) are ignored.

    Returns a dictionary:
      fields:   the field columns found (besides Product Type and Size)
      rows:     [{"product_type", "size", "values": {field: text}}]
      warnings: messages to show the user (rows skipped and why)
      errors:   problems that stop the file being saved
    """

    result = {"fields": [], "rows": [], "warnings": [], "errors": []}

    try:
        workbook = load_workbook(BytesIO(file_bytes), data_only=True, read_only=True)
    except Exception as error:
        result["errors"].append("This file could not be opened as Excel: " + str(error))
        return result

    rows_by_key = {}
    weight_warnings = []
    used_sheets = []

    for sheet in workbook.worksheets:
        if _read_sheet(sheet, result, rows_by_key, weight_warnings):
            used_sheets.append(sheet.title)

    workbook.close()

    if not used_sheets:
        result["errors"].append(
            f"No sheet has '{TYPE_COLUMN}' and '{SIZE_COLUMN}' in its first row."
        )
        return result

    if len(used_sheets) > 1:
        result["warnings"].append("Sheets read: " + ", ".join(used_sheets) + ".")

    result["warnings"] += weight_warnings

    empty_rows = [
        f"{row['product_type']} / {row['size']}"
        for row in result["rows"] if not any(row["values"].values())
    ]

    if empty_rows:
        result["warnings"].append(
            f"{len(empty_rows)} row(s) have no values yet, so nothing is "
            "checked for them: " + ", ".join(empty_rows)
        )

    if not result["rows"]:
        result["errors"].append("No rows with a Product Type and Size were found.")

    return result


def product_types(parsed):
    """The product types in a parsed or saved set, in file order."""

    types = []

    for row in parsed.get("rows", []):
        if row["product_type"] not in types:
            types.append(row["product_type"])

    return types


def rows_as_table(parsed):
    """Flatten rows into one table for display (one column per field)."""

    return [
        {TYPE_COLUMN: row["product_type"], SIZE_COLUMN: row["size"], **row["values"]}
        for row in parsed.get("rows", [])
    ]


def build_spec_for_audit(spec_set, product_type):
    """The dictionary that the audit uses: one set, one product type."""

    return {
        "set_name": spec_set["name"],
        "product_type": product_type,
        "rows": [
            row for row in spec_set["data"]["rows"]
            if row["product_type"] == product_type
        ]
    }


# =========================================
# 3. DATABASE STORAGE
# =========================================

def _ensure_table(connection):
    """Create the spec_sets table if it does not exist."""

    connection.execute("""
        CREATE TABLE IF NOT EXISTS spec_sets (
            set_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            file_name   TEXT NOT NULL DEFAULT '',
            uploaded_at TEXT NOT NULL,
            data_json   TEXT NOT NULL
        )
    """)

    connection.commit()


def save_spec_set(name, file_name, parsed):
    """
    Save a parsed template under a name. A set with the same name is
    replaced (so you can upload a corrected file). Returns the set_id.
    """

    name = " ".join(str(name or "").split())

    if not name:
        raise ValueError("Please give the specification set a name.")

    if parsed.get("errors"):
        raise ValueError("This file has errors and cannot be saved.")

    data = {"fields": parsed["fields"], "rows": parsed["rows"]}

    connection = get_connection()

    try:
        _ensure_table(connection)

        connection.execute("DELETE FROM spec_sets WHERE name = ?", (name,))

        cursor = connection.execute(
            """
            INSERT INTO spec_sets (name, file_name, uploaded_at, data_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                name,
                file_name or "",
                datetime.now().astimezone().isoformat(timespec="seconds"),
                json.dumps(data, ensure_ascii=False)
            )
        )

        connection.commit()

        return cursor.lastrowid

    finally:
        connection.close()


def list_spec_sets():
    """All saved sets (without their rows), newest first."""

    connection = get_connection()

    try:
        _ensure_table(connection)

        rows = connection.execute(
            "SELECT set_id, name, file_name, uploaded_at, data_json "
            "FROM spec_sets ORDER BY set_id DESC"
        ).fetchall()

        sets = []

        for row in rows:
            data = json.loads(row["data_json"])
            sets.append({
                "set_id": row["set_id"],
                "name": row["name"],
                "file_name": row["file_name"],
                "uploaded_at": row["uploaded_at"],
                "product_types": ", ".join(product_types(data)),
                "rows": len(data.get("rows", []))
            })

        return sets

    finally:
        connection.close()


def get_spec_set(set_id):
    """One saved set with its rows, or None."""

    connection = get_connection()

    try:
        _ensure_table(connection)

        row = connection.execute(
            "SELECT set_id, name, file_name, uploaded_at, data_json "
            "FROM spec_sets WHERE set_id = ?",
            (set_id,)
        ).fetchone()

        if row is None:
            return None

        return {
            "set_id": row["set_id"],
            "name": row["name"],
            "file_name": row["file_name"],
            "uploaded_at": row["uploaded_at"],
            "data": json.loads(row["data_json"])
        }

    finally:
        connection.close()


def delete_spec_set(set_id):
    """Delete one saved set. Audit history is not affected."""

    connection = get_connection()

    try:
        _ensure_table(connection)
        connection.execute("DELETE FROM spec_sets WHERE set_id = ?", (set_id,))
        connection.commit()

    finally:
        connection.close()
