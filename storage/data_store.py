# storage/data_store.py
#
# UPDATED: store_email() now accepts sensitive metadata parameters.
# fetch_sensitive() added for dashboard sensitive emails tab.
# get_summary_stats() now returns sensitive_count and by_sensitive_type.

from datetime import datetime

from database.db_manager import (
    init_db,
    email_exists,
    save_email as _db_save,
    get_all_emails,
    get_emails_by_category,
    get_sensitive_emails,
    get_stats,
    get_pending_approval_emails,
    update_reply_status,
    get_email_by_id,
)
from utils.logger import get_logger

logger = get_logger(__name__)


def initialize() -> None:
    """Initialize storage. Call once at app startup."""
    init_db()


def is_processed(email_id: str) -> bool:
    """Return True if this email has already been processed."""
    return email_exists(email_id)


def store_email(
    parsed_email: dict,
    summary: str = "",
    category: str = "",
    priority: str = "",
    reply_draft: str = "",
    sent_reply: bool = False,
    is_sensitive: bool = False,
    sensitive_type: str = None,
    reply_status: str = None,
) -> None:
    """
    Store a fully processed email with all AI-generated metadata.

    Parameters:
        is_sensitive:   True if sensitive_detector flagged this email
        sensitive_type: "OTP", "BANK_ALERT", "PASSWORD_RESET", etc.
        reply_status:   "AUTO_SENT" | "PENDING_APPROVAL" | "APPROVED" | "IGNORED" | None

    When is_sensitive=True, the body stored in summary/reply_draft
    should already be the MASKED version from sensitive_detector.
    """
    record = {
        "id":             parsed_email["id"],
        "sender":         parsed_email.get("sender", ""),
        "sender_email":   parsed_email.get("sender_email", ""),
        "subject":        parsed_email.get("subject", ""),
        "summary":        summary,
        "category":       category,
        "priority":       priority,
        "reply_draft":    reply_draft,
        "sent_reply":     sent_reply,
        "is_sensitive":   is_sensitive,
        "sensitive_type": sensitive_type,
        "reply_status":   reply_status,
        "thread_id":      parsed_email.get("thread_id", ""),
        "processed_at":   datetime.now().isoformat(),
    }

    _db_save(record)

    sensitive_tag = f" [🔐 {sensitive_type}]" if is_sensitive else ""
    decision_tag  = f" [🧠 {reply_status}]" if reply_status else ""
    logger.info(
        "Stored: [%s]%s%s %s | %s",
        category or "?",
        sensitive_tag,
        decision_tag,
        (priority.split("\n")[0] if priority else "?"),
        parsed_email.get("subject", "?")[:40],
    )


def fetch_recent(limit: int = 200) -> list[dict]:
    """Get recent processed emails for the dashboard."""
    return get_all_emails(limit=limit)


def fetch_by_category(category: str) -> list[dict]:
    """Get emails filtered by category."""
    return get_emails_by_category(category)


def fetch_sensitive(limit: int = 50) -> list[dict]:
    """Get all sensitive emails for the dashboard sensitive tab."""
    return get_sensitive_emails(limit=limit)


def fetch_pending_approval(limit: int = 50) -> list[dict]:
    """Get emails awaiting human approval — for the dashboard Pending tab."""
    return get_pending_approval_emails(limit=limit)


def update_email_status(email_id: str, status: str) -> None:
    """Update the reply_status of an email after user action via Telegram."""
    update_reply_status(email_id, status)


def fetch_email_by_id(email_id: str) -> dict | None:
    """Fetch a single email by ID — used by Telegram callback handler."""
    return get_email_by_id(email_id)


def get_summary_stats() -> dict:
    """Get aggregate stats for the dashboard metrics."""
    return get_stats()
