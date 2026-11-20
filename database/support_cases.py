"""
Support case tracker.

Stores support case drafts in the same SQLite database as the audit
history. The app never submits anything to Amazon. A draft is prepared
here, you copy it into Seller Central yourself, and then you record the
Amazon case ID and status in this tracker.
"""

from datetime import datetime

from database.db import get_connection


# Statuses you can set manually, in the order they usually happen.
CASE_STATUSES = [
    "Draft",
    "Ready to Submit",
    "Submitted by Me",
    "Awaiting Amazon Reply",
    "Resolved",
    "Rejected",
]


def ensure_table(connection):
    """Create the support_cases table if it does not exist yet."""

    connection.execute("""
        CREATE TABLE IF NOT EXISTS support_cases (
            case_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            asin            TEXT NOT NULL,
            run_id          INTEGER,
            title           TEXT NOT NULL,
            draft_text      TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'Draft',
            amazon_case_id  TEXT NOT NULL DEFAULT '',
            notes           TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )
    """)

    connection.commit()


def get_asins_for_run(run_id):
    """Return the ASINs that were read in one saved run."""

    connection = get_connection()

    try:
        ensure_table(connection)

        rows = connection.execute(
            "SELECT DISTINCT asin FROM audit_products WHERE run_id = ? ORDER BY asin",
            (run_id,)
        ).fetchall()

        return [row["asin"] for row in rows]

    finally:
        connection.close()


def get_findings_for_run_asin(run_id, asin):
    """Return the saved findings for one product in one run."""

    connection = get_connection()

    try:
        ensure_table(connection)

        rows = connection.execute(
            """
            SELECT i.location, i.detail, i.original_text, i.suggested_text
            FROM audit_issues i
            JOIN audit_products p ON p.product_id = i.product_id
            WHERE p.run_id = ? AND p.asin = ?
            ORDER BY i.location
            """,
            (run_id, asin)
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def build_draft(asin, findings):
    """
    Write a plain, factual draft from the saved findings.

    The draft describes what was found and where. It does not claim
    an Amazon policy breach, because the findings come from project
    rules (British English), not from Amazon policy.
    """

    lines = [
        f"Product ASIN: {asin}",
        "",
        "We are reviewing our listing content and have identified the following",
        "wording items that should be corrected:",
        "",
    ]

    for number, finding in enumerate(findings, start=1):

        lines.append(f"{number}. Location: {finding['location']}")
        lines.append(f"   Finding: {finding['detail']}")
        lines.append("")

    lines.append("We would be grateful if these items could be reviewed.")
    lines.append("Please let us know if any further information is required.")

    return "\n".join(lines)


def create_case(asin, run_id, title, draft_text):
    """Save a new case draft and return its case_id."""

    connection = get_connection()

    try:
        ensure_table(connection)

        now = datetime.now().astimezone().isoformat()

        cursor = connection.execute(
            """
            INSERT INTO support_cases
                (asin, run_id, title, draft_text, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'Draft', ?, ?)
            """,
            (asin, run_id, title, draft_text, now, now)
        )

        connection.commit()

        return cursor.lastrowid

    finally:
        connection.close()


def list_cases():
    """Return every case, newest first."""

    connection = get_connection()

    try:
        ensure_table(connection)

        rows = connection.execute(
            """
            SELECT case_id, asin, run_id, title, status,
                   amazon_case_id, notes, created_at, updated_at
            FROM support_cases
            ORDER BY case_id DESC
            """
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_case(case_id):
    """Return one case with its full draft text, or None."""

    connection = get_connection()

    try:
        ensure_table(connection)

        row = connection.execute(
            "SELECT * FROM support_cases WHERE case_id = ?",
            (case_id,)
        ).fetchone()

        return dict(row) if row else None

    finally:
        connection.close()


def update_case(case_id, status, amazon_case_id, notes):
    """Save the status, Amazon case ID and notes you entered."""

    connection = get_connection()

    try:
        ensure_table(connection)

        connection.execute(
            """
            UPDATE support_cases
            SET status = ?, amazon_case_id = ?, notes = ?, updated_at = ?
            WHERE case_id = ?
            """,
            (
                status,
                amazon_case_id.strip(),
                notes.strip(),
                datetime.now().astimezone().isoformat(),
                case_id
            )
        )

        connection.commit()

    finally:
        connection.close()