"""
History Excel export.

Builds an Excel workbook for one saved run from the SQLite database.
The workbook has three sheets:
- Run Info: when the run was made and what it covered.
- Products: one row per product as it was read in that run.
- Issues: every finding, with its current correction status and note.

Correction statuses are read from the live tracker, so the export always
shows the latest status, even for runs made before the status was set.
"""

from database.db import get_connection
from reports.excel_generator import build_workbook


def fetch_run_info(run_id):
    """Return the run's basic details as one dictionary, or None."""

    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT run_id, run_type, size_filter, started_at, product_count
            FROM audit_runs
            WHERE run_id = ?
            """,
            (run_id,)
        ).fetchone()

        return dict(row) if row else None

    finally:
        connection.close()


def fetch_run_products(run_id):
    """Return every product read in one run, in the order it was audited."""

    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT asin, colour, size, overall_status, price, seller,
                   location_verified, checked_at
            FROM audit_products
            WHERE run_id = ?
            ORDER BY product_id
            """,
            (run_id,)
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def fetch_run_issues(run_id):
    """
    Return every finding in one run, joined with its correction status.
    The status is matched by fingerprint, so it follows the finding
    across runs.
    """

    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT p.asin, i.location, i.category, i.detail,
                   i.original_text, i.suggested_text,
                   s.status, s.note
            FROM audit_issues i
            JOIN audit_products p ON p.product_id = i.product_id
            LEFT JOIN issue_status s ON s.fingerprint = i.fingerprint
            WHERE p.run_id = ?
            ORDER BY p.asin, i.location
            """,
            (run_id,)
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def build_run_workbook(run_id):
    """
    Return the workbook for one run as bytes, ready for st.download_button.
    """

    info = fetch_run_info(run_id) or {}

    info_rows = [
        {"Field": "Run ID", "Value": info.get("run_id", "")},
        {"Field": "Run type", "Value": info.get("run_type", "")},
        {"Field": "Size filter", "Value": info.get("size_filter") or "All sizes"},
        {"Field": "Started at", "Value": info.get("started_at", "")},
        {"Field": "Products", "Value": info.get("product_count", 0)},
    ]

    product_headers = [
        "ASIN", "Colour", "Size", "Overall Status", "Price",
        "Seller", "Location Verified", "Checked At"
    ]

    product_rows = [
        {
            "ASIN": row["asin"],
            "Colour": row["colour"],
            "Size": row["size"],
            "Overall Status": row["overall_status"],
            "Price": row["price"],
            "Seller": row["seller"],
            "Location Verified": "Yes" if row["location_verified"] else "No",
            "Checked At": row["checked_at"],
        }
        for row in fetch_run_products(run_id)
    ]

    issue_headers = [
        "ASIN", "Where", "Category", "Detail", "Original Text",
        "Suggested Text", "Correction Status", "Note"
    ]

    issue_rows = [
        {
            "ASIN": row["asin"],
            "Where": row["location"],
            "Category": row["category"],
            "Detail": row["detail"],
            "Original Text": row["original_text"],
            "Suggested Text": row["suggested_text"],
            "Correction Status": row["status"] or "Not Started",
            "Note": row["note"] or "",
        }
        for row in fetch_run_issues(run_id)
    ]

    return build_workbook([
        ("Run Info", ["Field", "Value"], info_rows),
        ("Products", product_headers, product_rows),
        ("Issues", issue_headers, issue_rows),
    ])