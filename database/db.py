"""
Database connection and table setup.

Stores permanent audit history in one SQLite file: data/audit_history.db.
SQLite is built into Python, so nothing needs installing.

The tables are created automatically the first time the app runs.
"""

import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / "data"
DB_PATH = DB_DIR / "audit_history.db"


def get_connection():
    """
    Open a connection to the audit database.
    Creates the folder and tables if they do not exist yet.
    """

    DB_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)

    # Return rows that can be read by column name, e.g. row["asin"].
    connection.row_factory = sqlite3.Row

    # Enforce links between tables (e.g. an issue must belong to a run).
    connection.execute("PRAGMA foreign_keys = ON")

    create_tables(connection)

    return connection


def create_tables(connection):
    """
    Create the tables if they are missing. Existing data is never removed.

    audit_runs      one row per batch or matrix run
    audit_products  one row per product checked in a run (immutable snapshot)
    audit_issues    one row per finding, linked to its product
    issue_status    the correction status of each finding, kept across runs
    """

    connection.executescript("""
        CREATE TABLE IF NOT EXISTS audit_runs (
            run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            run_type      TEXT NOT NULL,
            size_filter   TEXT,
            started_at    TEXT NOT NULL,
            product_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS audit_products (
            product_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id         INTEGER NOT NULL,
            asin           TEXT NOT NULL,
            colour         TEXT,
            size           TEXT,
            overall_status TEXT,
            price          TEXT,
            seller         TEXT,
            location_verified INTEGER NOT NULL DEFAULT 0,
            checked_at     TEXT,
            FOREIGN KEY (run_id) REFERENCES audit_runs(run_id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS audit_issues (
            issue_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id    INTEGER NOT NULL,
            asin          TEXT NOT NULL,
            fingerprint   TEXT NOT NULL,
            category      TEXT,
            location      TEXT,
            detail        TEXT,
            original_text TEXT,
            suggested_text TEXT,
            FOREIGN KEY (product_id) REFERENCES audit_products(product_id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS issue_status (
            fingerprint  TEXT PRIMARY KEY,
            asin         TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'Not Started',
            note         TEXT,
            updated_at   TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_products_asin ON audit_products(asin);
        CREATE INDEX IF NOT EXISTS idx_issues_asin ON audit_issues(asin);
    """)

    connection.commit()


if __name__ == "__main__":

    # Quick check. Run: python -m database.db
    connection = get_connection()

    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()

    print("Database file:", DB_PATH)
    print("Tables:", [row["name"] for row in tables])

    connection.close()