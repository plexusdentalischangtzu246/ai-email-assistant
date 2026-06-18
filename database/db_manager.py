# database/db_manager.py
#
# UPDATED: Added columns to support the Human Decision Detection Layer:
#
#   reply_status   (TEXT) — AUTO_SENT | PENDING_APPROVAL | APPROVED | IGNORED
#   thread_id      (TEXT) — Gmail thread ID for reply linking
#
# Existing columns unchanged:
#   is_sensitive  (INTEGER 0/1) — was this email flagged as sensitive?
#   sensitive_type (TEXT)       — which type: OTP, BANK_ALERT, etc.
#
# WHY ADD COLUMNS HERE AND NOT ELSEWHERE:
# The database is the single source of truth. The dashboard reads from here.
# If we store sensitive metadata anywhere else we'd have sync issues.
#
# MIGRATION NOTE:
# If you already have an emails.db from a previous version, the
# ADD COLUMN statements handle migration safely — they only add the
# columns if they don't exist yet. Your existing data is untouched.

import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

DB_PATH = os.getenv("DB_PATH", "emails.db")


@contextmanager
def _get_connection():
    """Context manager — always commits or rolls back, always closes."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    Create tables and indexes. Safe to call on every startup.
    Also handles migration for existing databases via ALTER TABLE.
    """
    logger.info("Initializing database: %s", DB_PATH)

    with _get_connection() as conn:
        # Create table with all columns including new sensitive fields
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS processed_emails (
                id             TEXT PRIMARY KEY,
                sender         TEXT NOT NULL DEFAULT '',
                sender_email   TEXT NOT NULL DEFAULT '',
                subject        TEXT NOT NULL DEFAULT '',
                summary        TEXT,
                category       TEXT,
                sensitive_type TEXT,
                is_sensitive   INTEGER DEFAULT 0,
                priority       TEXT,
                reply_draft    TEXT,
                sent_reply     INTEGER DEFAULT 0,
                reply_status   TEXT,
                thread_id      TEXT,
                processed_at   TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_processed_at
                ON processed_emails(processed_at);

            CREATE INDEX IF NOT EXISTS idx_category
                ON processed_emails(category);

            CREATE INDEX IF NOT EXISTS idx_is_sensitive
                ON processed_emails(is_sensitive);

            CREATE INDEX IF NOT EXISTS idx_reply_status
                ON processed_emails(reply_status);
        """)

        # ── Migration: add columns to existing databases ──────────────────────
        # If the user already has an emails.db from a previous version,
        # these ALTER TABLE statements add the missing columns safely.
        # "ADD COLUMN IF NOT EXISTS" is supported in SQLite 3.37.0+.
        # For older SQLite, we use a try/except approach.
        existing_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(processed_emails)")
        }

        migration_cols = {
            "is_sensitive":   "INTEGER DEFAULT 0",
            "sensitive_type": "TEXT",
            "reply_status":   "TEXT",
            "thread_id":      "TEXT",
        }

        for col_name, col_def in migration_cols.items():
            if col_name not in existing_cols:
                conn.execute(
                    f"ALTER TABLE processed_emails ADD COLUMN {col_name} {col_def}"
                )
                logger.info("DB migration: added column '%s'", col_name)

    logger.info("Database ready")


def email_exists(email_id: str) -> bool:
    """Check if this email has already been processed (deduplication guard)."""
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM processed_emails WHERE id = ?", (email_id,)
        ).fetchone()
        return row is not None


def save_email(data: dict) -> None:
    """Save or update a processed email record."""
    logger.debug("Saving: %s", data.get("subject", "?")[:50])

    with _get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO processed_emails
                (id, sender, sender_email, subject, summary, category,
                 sensitive_type, is_sensitive, priority, reply_draft,
                 sent_reply, reply_status, thread_id, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["id"],
            data.get("sender", ""),
            data.get("sender_email", ""),
            data.get("subject", ""),
            data.get("summary", ""),
            data.get("category", ""),
            data.get("sensitive_type"),
            int(data.get("is_sensitive", False)),
            data.get("priority", ""),
            data.get("reply_draft", ""),
            int(data.get("sent_reply", False)),
            data.get("reply_status"),
            data.get("thread_id", ""),
            data.get("processed_at", datetime.now().isoformat()),
        ))


def get_all_emails(limit: int = 200) -> list[dict]:
    """Fetch most recent emails, newest first."""
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM processed_emails ORDER BY processed_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


def get_emails_by_category(category: str) -> list[dict]:
    """Fetch emails filtered by category."""
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM processed_emails WHERE category = ? ORDER BY processed_at DESC",
            (category,)
        ).fetchall()
        return [dict(row) for row in rows]


def get_sensitive_emails(limit: int = 50) -> list[dict]:
    """Fetch all sensitive emails — used by dashboard sensitive tab."""
    with _get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM processed_emails
               WHERE is_sensitive = 1
               ORDER BY processed_at DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


def get_stats() -> dict:
    """Return aggregate statistics for the dashboard."""
    with _get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM processed_emails"
        ).fetchone()[0]

        sensitive_count = conn.execute(
            "SELECT COUNT(*) FROM processed_emails WHERE is_sensitive = 1"
        ).fetchone()[0]

        by_cat = conn.execute(
            "SELECT category, COUNT(*) as count FROM processed_emails GROUP BY category"
        ).fetchall()

        by_sensitive_type = conn.execute(
            """SELECT sensitive_type, COUNT(*) as count
               FROM processed_emails
               WHERE is_sensitive = 1 AND sensitive_type IS NOT NULL
               GROUP BY sensitive_type"""
        ).fetchall()

        # ── Human Decision Layer stats ─────────────────────────────────────
        pending_approval = conn.execute(
            "SELECT COUNT(*) FROM processed_emails WHERE reply_status = 'PENDING_APPROVAL'"
        ).fetchone()[0]

        approved_replies = conn.execute(
            "SELECT COUNT(*) FROM processed_emails WHERE reply_status = 'APPROVED'"
        ).fetchone()[0]

        ignored_emails = conn.execute(
            "SELECT COUNT(*) FROM processed_emails WHERE reply_status = 'IGNORED'"
        ).fetchone()[0]

        decision_emails = conn.execute(
            "SELECT COUNT(*) FROM processed_emails "
            "WHERE reply_status IN ('PENDING_APPROVAL', 'APPROVED', 'IGNORED')"
        ).fetchone()[0]

        return {
            "total": total,
            "sensitive_count": sensitive_count,
            "by_category": {row["category"]: row["count"] for row in by_cat},
            "by_sensitive_type": {
                row["sensitive_type"]: row["count"] for row in by_sensitive_type
            },
            # Human Decision Layer
            "pending_approval":  pending_approval,
            "approved_replies":  approved_replies,
            "ignored_emails":    ignored_emails,
            "decision_emails":   decision_emails,
        }


def get_pending_approval_emails(limit: int = 50) -> list[dict]:
    """Fetch emails awaiting human approval — for the dashboard Pending tab."""
    with _get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM processed_emails
               WHERE reply_status = 'PENDING_APPROVAL'
               ORDER BY processed_at DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


def update_reply_status(email_id: str, status: str) -> None:
    """
    Update the reply_status of a processed email.

    Valid status values: AUTO_SENT | PENDING_APPROVAL | APPROVED | IGNORED

    Called by telegram_approval.py when the user taps an inline button.
    """
    valid_statuses = {"AUTO_SENT", "PENDING_APPROVAL", "APPROVED", "IGNORED"}
    if status not in valid_statuses:
        logger.warning("Invalid reply_status '%s' — ignoring update", status)
        return

    with _get_connection() as conn:
        conn.execute(
            "UPDATE processed_emails SET reply_status = ? WHERE id = ?",
            (status, email_id)
        )
    logger.info("Updated reply_status=%s for email_id=%s", status, email_id)


def get_email_by_id(email_id: str) -> dict | None:
    """Fetch a single email record by its ID. Returns None if not found."""
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM processed_emails WHERE id = ?",
            (email_id,)
        ).fetchone()
        return dict(row) if row else None
