"""
History service.

Saves every batch or matrix run to the database, and compares a new
audit with the previous one so each issue can be marked as:
- STILL PRESENT: found before and found again
- VERIFIED FIXED: found before, not found now (product read successfully)
- NEW: found now, not found before

An issue is only marked VERIFIED FIXED when the product was read
successfully this time. A failed read never counts as a fix.
"""

import hashlib
from datetime import datetime

from database.db import get_connection
from services.issue_report import issues_for_product


# Severities that are real problems to correct (saved and tracked).
# "Check" (bot could not confirm) and "Advice" are not tracked.
TRACKED_SEVERITIES = ("High", "Medium", "Low")


def make_fingerprint(asin, category, location, original_text):
    """
    Build a stable ID for one issue, so the same problem is recognised
    across runs even though the audit creates new numbers each time.
    """

    raw = "|".join([asin, category or "", location or "", original_text or ""])

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def issue_kind(category, location):
    """
    Which optional check produced an issue:
      "spec"   - specification check (only runs when a template is chosen)
      "design" - A+ design match (only runs when that box is ticked)
      "ocr"    - text inside images (only runs when that box is ticked)
      "always" - every other check runs on every audit
    """

    text = f"{category} {location}".lower()

    if "image text" in text:
        return "ocr"

    if "specification" in text:
        return "spec"

    if "a+ design" in text or "colour check" in text or "video" in text:
        return "design"

    return "always"


def trackable_issues(result):
    """
    Every real problem of one product (High, Medium or Low), ready to
    save and track: Featured Offer, listing quality, spelling,
    specification, A+ / Brand Story / images.

    Each: {"fingerprint", "category", "location", "detail",
           "original_text", "suggested_text"}.
    The fingerprint ignores the changing value (e.g. which other seller
    holds the Featured Offer), so the same problem keeps the same ID
    across runs and its correction status is kept.
    """

    asin = result.get("asin", "")

    spelling = {
        (issue.get("location", ""), "Spelling: " + str(issue.get("detected_term", ""))): issue
        for issue in (result.get("spelling") or {}).get("issues") or []
    }

    tracked = []
    seen = set()

    for row in issues_for_product(result):

        if row["Severity"] not in TRACKED_SEVERITIES:
            continue

        category = f"{row['Severity']} | {row['Issue']}"

        legacy = spelling.get((row["Area"], row["Issue"]))

        if legacy:
            # Same ID as earlier versions, so old statuses are kept.
            fingerprint = make_fingerprint(
                asin, legacy.get("category", ""), legacy.get("location", ""),
                legacy.get("original_text", "")
            )
        else:
            fingerprint = make_fingerprint(asin, row["Issue"], row["Area"], "")

        if fingerprint in seen:
            continue

        seen.add(fingerprint)

        tracked.append({
            "fingerprint": fingerprint,
            "category": category,
            "location": row["Area"],
            "detail": f"{row['Issue']}. {row['What To Do']}".strip(),
            "original_text": row["Amazon Shows"],
            "suggested_text": row["Should Be"],
        })

    return tracked


def save_run(run_type, size_filter, results, rows):
    """
    Store one run and all its products and issues.
    Returns the new run_id.
    """

    connection = get_connection()

    try:

        cursor = connection.execute(
            """
            INSERT INTO audit_runs (run_type, size_filter, started_at, product_count)
            VALUES (?, ?, ?, ?)
            """,
            (
                run_type,
                size_filter or "",
                datetime.now().astimezone().isoformat(),
                len(results)
            )
        )

        run_id = cursor.lastrowid

        for result in results:

            buy_box = result.get("buy_box") or {}
            location = buy_box.get("location") or {}
            content = result.get("content") or {}
            technical = content.get("technical_details") or {}
            spelling = result.get("spelling") or {}

            asin = result.get("asin", "")

            product_cursor = connection.execute(
                """
                INSERT INTO audit_products
                    (run_id, asin, colour, size, overall_status, price,
                     seller, location_verified, checked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    asin,
                    technical.get("Colour", ""),
                    technical.get("Size", size_filter or ""),
                    result.get("overall_status", ""),
                    buy_box.get("price", ""),
                    buy_box.get("seller", ""),
                    1 if location.get("verified") else 0,
                    result.get("completed_at", "")
                )
            )

            product_id = product_cursor.lastrowid

            for issue in trackable_issues(result):

                connection.execute(
                    """
                    INSERT INTO audit_issues
                        (product_id, asin, fingerprint, category, location,
                         detail, original_text, suggested_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        product_id,
                        asin,
                        issue["fingerprint"],
                        issue["category"],
                        issue["location"],
                        issue["detail"],
                        issue["original_text"],
                        issue["suggested_text"]
                    )
                )

                # Make sure every issue has a status row (default: Not Started).
                connection.execute(
                    """
                    INSERT OR IGNORE INTO issue_status
                        (fingerprint, asin, status, updated_at)
                    VALUES (?, ?, 'Not Started', ?)
                    """,
                    (issue["fingerprint"], asin, datetime.now().astimezone().isoformat())
                )

        connection.commit()

        return run_id

    finally:

        connection.close()


def get_previous_run_for_asin(asin, before_run_id=None):
    """
    Return the most recent earlier snapshot of one product as a dictionary,
    or None if the product has never been audited before.
    """

    connection = get_connection()

    try:

        query = """
            SELECT p.product_id, p.run_id, p.overall_status, p.location_verified
            FROM audit_products p
            WHERE p.asin = ?
        """

        parameters = [asin]

        if before_run_id is not None:
            query += " AND p.run_id < ?"
            parameters.append(before_run_id)

        query += " ORDER BY p.run_id DESC LIMIT 1"

        product = connection.execute(query, parameters).fetchone()

        if product is None:
            return None

        issues = connection.execute(
            """
            SELECT i.fingerprint, i.category, i.location, i.detail,
                   i.original_text, i.suggested_text
            FROM audit_issues i
            WHERE i.product_id = ?
            """,
            (product["product_id"],)
        ).fetchall()

        return {
            "run_id": product["run_id"],
            "location_verified": bool(product["location_verified"]),
            "issues": [dict(issue) for issue in issues]
        }

    finally:

        connection.close()


def compare_with_previous(asin, current_issues, current_location_ok, run_id):
    """
    Compare current issues for one ASIN with its last saved audit.

    current_issues: list of issue dictionaries with a "fingerprint" key.
    Returns a list of comparison rows for the website.
    """

    previous = get_previous_run_for_asin(asin, before_run_id=run_id)

    if previous is None:

        return [{
            "ASIN": asin,
            "Issue": issue.get("location", ""),
            "Recheck Result": "FIRST AUDIT",
            "Detail": issue.get("detail", "")
        } for issue in current_issues]

    current_fingerprints = {issue["fingerprint"] for issue in current_issues}

    previous_fingerprints = {issue["fingerprint"] for issue in previous["issues"]}

    rows = []

    for issue in previous["issues"]:

        if issue["fingerprint"] in current_fingerprints:

            result = "STILL PRESENT"

        elif current_location_ok:

            result = "VERIFIED FIXED"

        else:

            # The product could not be read reliably this time, so the
            # issue cannot be marked fixed.
            result = "NOT VERIFIED - product not read"

        rows.append({
            "ASIN": asin,
            "Issue": issue.get("location", ""),
            "Recheck Result": result,
            "Detail": issue.get("detail", "")
        })

    for issue in current_issues:

        if issue["fingerprint"] not in previous_fingerprints:

            rows.append({
                "ASIN": asin,
                "Issue": issue.get("location", ""),
                "Recheck Result": "NEW",
                "Detail": issue.get("detail", "")
            })

    return rows


def get_issue_statuses(fingerprints):
    """Return a dictionary of fingerprint -> status for the given issues."""

    if not fingerprints:
        return {}

    connection = get_connection()

    try:

        placeholders = ",".join("?" for _ in fingerprints)

        rows = connection.execute(
            f"SELECT fingerprint, status FROM issue_status "
            f"WHERE fingerprint IN ({placeholders})",
            list(fingerprints)
        ).fetchall()

        return {row["fingerprint"]: row["status"] for row in rows}

    finally:

        connection.close()


def set_issue_status(fingerprint, asin, status, note=""):
    """Save the correction status of one issue, e.g. 'Corrected by Seller'."""

    connection = get_connection()

    try:

        connection.execute(
            """
            INSERT INTO issue_status (fingerprint, asin, status, note, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(fingerprint) DO UPDATE SET
                status = excluded.status,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (
                fingerprint,
                asin,
                status,
                note,
                datetime.now().astimezone().isoformat()
            )
        )

        connection.commit()

    finally:

        connection.close()


def get_all_issues_with_status():
    """
    Return every saved issue with its current correction status.
    Used by the Correction Tracker page.
    """

    connection = get_connection()

    try:

        rows = connection.execute(
            """
            SELECT i.asin, i.fingerprint, i.category, i.location, i.detail,
                   i.original_text, i.suggested_text, s.status, s.note, s.updated_at
            FROM audit_issues i
            LEFT JOIN issue_status s ON s.fingerprint = i.fingerprint
            GROUP BY i.fingerprint
            ORDER BY i.asin, i.location
            """
        ).fetchall()

        return [dict(row) for row in rows]

    finally:

        connection.close()


def get_run_list():
    """Return all saved runs, newest first, for the Audit History page."""

    connection = get_connection()

    try:

        rows = connection.execute(
            """
            SELECT run_id, run_type, size_filter, started_at, product_count
            FROM audit_runs
            ORDER BY run_id DESC
            """
        ).fetchall()

        return [dict(row) for row in rows]

    finally:

        connection.close()
def compare_recheck_against_run(run_id, asin, current_issues, location_ok, checks_run=None):
    """
    Compare a recheck with the saved state of one product in an earlier run.

    checks_run: the optional checks that ran this time, e.g. {"spec",
    "design"}. An issue from a check that did NOT run this time is
    "NOT CHECKED THIS TIME", never "VERIFIED FIXED".
    """

    checks_run = set(checks_run or ()) | {"always"}

    connection = get_connection()

    try:

        product = connection.execute(
            "SELECT product_id FROM audit_products WHERE run_id = ? AND asin = ?",
            (run_id, asin)
        ).fetchone()

        previous_issues = []

        if product is not None:

            rows = connection.execute(
                """
                SELECT fingerprint, category, location, detail,
                       original_text, suggested_text
                FROM audit_issues WHERE product_id = ?
                """,
                (product["product_id"],)
            ).fetchall()

            previous_issues = [dict(row) for row in rows]

    finally:

        connection.close()

    previous_fingerprints = {issue["fingerprint"] for issue in previous_issues}
    current_fingerprints = {issue["fingerprint"] for issue in current_issues}

    rows = []

    for issue in previous_issues:

        if issue["fingerprint"] in current_fingerprints:
            outcome = "STILL PRESENT"
        elif issue_kind(issue.get("category"), issue.get("location")) not in checks_run:
            outcome = "NOT CHECKED THIS TIME"
        elif location_ok:
            outcome = "VERIFIED FIXED"
        else:
            outcome = "NOT VERIFIED - product not read"

        if outcome == "VERIFIED FIXED":
            # Keep the Correction Tracker in step with the live page.
            set_issue_status(issue["fingerprint"], asin, "Verified Fixed",
                             f"Confirmed by recheck of run {run_id}")
        elif outcome == "STILL PRESENT":
            set_issue_status(issue["fingerprint"], asin, "Still Present",
                             f"Found again in recheck of run {run_id}")

        rows.append({
            "ASIN": asin,
            "Issue": issue["location"],
            "Problem": issue.get("category", ""),
            "Recheck Result": outcome,
            "Detail": issue["detail"]
        })

    for issue in current_issues:

        if issue["fingerprint"] not in previous_fingerprints:
            rows.append({
                "ASIN": asin,
                "Issue": issue["location"],
                "Problem": issue.get("category", ""),
                "Recheck Result": "NEW",
                "Detail": issue["detail"]
            })

    return rows