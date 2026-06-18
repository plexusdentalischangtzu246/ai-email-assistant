# email_engine/fetcher.py
#
# WHY THIS FILE EXISTS:
# This file's only job is to talk to the Gmail API and get raw email data.
# It knows about API calls, query syntax, pagination, and error handling.
# It does NOT know how to parse emails — that's parser.py's job.
#
# WHY SEPARATE FROM parser.py:
# Imagine Gmail changes their API response format next year.
# You only change this file. parser.py is untouched.
# Now imagine you switch from Gmail API to IMAP.
# You only rewrite this file. Everything else stays the same.
# This is the Single Responsibility Principle in practice.

from auth.gmail_auth import get_gmail_service
from utils.logger import get_logger

logger = get_logger(__name__)


def fetch_emails(max_results: int = 5, query: str = "is:unread") -> list[dict]:
    """
    Fetch emails from Gmail matching the given search query.

    Args:
        max_results: How many emails to fetch (1–500)
        query:       Gmail search query string
                     "is:unread"               → all unread
                     "is:unread newer_than:1d" → unread from last 24h
                     "from:boss@work.com"      → from specific sender

    Returns:
        List of full Gmail message payload dicts.
        Empty list if no matching emails found.

    Each item in the list is a raw Gmail payload — a deeply nested dict
    that parser.py knows how to decode into readable email data.
    """

    logger.info("Fetching up to %d emails — query: '%s'", max_results, query)

    try:
        service = get_gmail_service()

        # ── Step 1: Get a list of matching message IDs ────────────────────────
        # messages.list() is FAST — it returns only IDs, not full content.
        # Think of this as getting a list of envelopes before opening them.
        list_response = service.users().messages().list(
            userId="me",
            maxResults=max_results,
            q=query,
        ).execute()

        message_stubs = list_response.get("messages", [])

        if not message_stubs:
            logger.info("No emails found matching query: '%s'", query)
            return []

        logger.info("Found %d email(s). Fetching full content...", len(message_stubs))

        # ── Step 2: Fetch the full content for each message ID ────────────────
        # messages.get() with format="full" returns the complete email:
        # headers (From, Subject, Date), body, labels, attachments info.
        full_messages = []

        for stub in message_stubs:
            try:
                full_msg = service.users().messages().get(
                    userId="me",
                    id=stub["id"],
                    format="full",
                ).execute()
                full_messages.append(full_msg)

            except Exception as e:
                # One bad email should not stop processing the rest.
                # Log it and move on.
                logger.warning("Could not fetch message %s: %s", stub["id"], e)
                continue

        logger.info("Successfully fetched %d email(s)", len(full_messages))
        return full_messages

    except Exception as e:
        logger.error("Gmail fetch failed: %s", e)
        raise
