# email_engine/parser.py
#
# WHY THIS FILE EXISTS:
# Gmail API returns emails in MIME format, base64-encoded.
# This is completely unreadable as-is. This file decodes everything
# into a clean Python dictionary with plain readable text.
#
# WHY IS THIS COMPLEX:
# Emails can be structured in many ways:
#   - Simple: one text/plain part
#   - HTML only: one text/html part (needs tag stripping)
#   - Multipart/alternative: plain + html versions of same content
#   - Multipart/mixed: content + attachments
#   - Nested: multipart inside multipart
# This file handles ALL of these cases reliably.
#
# FIX FROM YOUR ORIGINAL CODE:
# Your parser was missing thread_id and sender_email fields.
# The sender_email field is needed by gmail_sender.py to know
# WHERE to send the reply. Without it, you'd be replying to the
# full "Name <email>" string instead of just the email address.

import base64
import re
from bs4 import BeautifulSoup
from utils.logger import get_logger

logger = get_logger(__name__)


def parse_email(raw_message: dict) -> dict:
    """
    Parse a raw Gmail API message into a clean, readable dictionary.

    Args:
        raw_message: Full Gmail message payload from messages.get()

    Returns:
        Dict with these keys:
            id          — Gmail message ID (unique, used for deduplication)
            thread_id   — Gmail thread ID (for grouping conversation chains)
            subject     — Email subject line
            sender      — Full sender string "Name <email@domain.com>"
            sender_email — Just the email address "email@domain.com"
            date        — Send date string
            body        — Clean plain text body (HTML stripped if needed)
            snippet     — Gmail's auto-generated 200-char preview
            labels      — List of Gmail labels ["INBOX", "UNREAD", ...]
    """

    payload = raw_message.get("payload", {})
    headers = payload.get("headers", [])

    # Build a dict from the headers list for fast O(1) lookup.
    # Gmail returns headers as a list of {name, value} objects.
    # We lowercase the keys so "From" and "from" both work.
    header_map = {h["name"].lower(): h["value"] for h in headers}

    subject      = header_map.get("subject", "(No Subject)")
    sender       = header_map.get("from", "(Unknown Sender)")
    date         = header_map.get("date", "(Unknown Date)")
    sender_email = _extract_email(sender)
    body         = _extract_body(payload)
    labels       = raw_message.get("labelIds", [])

    parsed = {
        "id":           raw_message["id"],
        "thread_id":    raw_message.get("threadId", ""),
        "subject":      subject,
        "sender":       sender,
        "sender_email": sender_email,
        "date":         date,
        "body":         body,
        "snippet":      raw_message.get("snippet", ""),
        "labels":       labels,
    }

    logger.debug("Parsed: [%s] from %s", subject[:50], sender_email)
    return parsed


def _extract_email(sender_string: str) -> str:
    """
    Pull the actual email address out of a sender string.

    "Alice Johnson <alice@company.com>"  →  "alice@company.com"
    "alice@company.com"                  →  "alice@company.com"
    "noreply@service.com"                →  "noreply@service.com"
    """
    match = re.search(r"<([^>]+)>", sender_string)
    if match:
        return match.group(1).strip()
    return sender_string.strip()


def _extract_body(payload: dict) -> str:
    """
    Recursively walk the MIME payload tree to find the best body text.

    Priority:
    1. text/plain  — cleanest, best for LLM processing
    2. text/html   — stripped of tags
    3. Nested multipart — recurse deeper
    """

    mime_type = payload.get("mimeType", "")

    # Direct text/plain part — best case
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return _decode(data)

    # Direct HTML part — strip tags
    if mime_type == "text/html":
        data = payload.get("body", {}).get("data", "")
        html = _decode(data)
        return _strip_html(html)

    # Multipart — look through sub-parts
    if "multipart" in mime_type:
        parts = payload.get("parts", [])

        # First pass: prefer plain text
        for part in parts:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                text = _decode(data)
                if text.strip():
                    return text

        # Second pass: accept HTML
        for part in parts:
            if part.get("mimeType") == "text/html":
                data = part.get("body", {}).get("data", "")
                text = _strip_html(_decode(data))
                if text.strip():
                    return text

        # Third pass: recurse into nested multipart
        for part in parts:
            result = _extract_body(part)
            if result and result != "(No readable body found)":
                return result

    return "(No readable body found)"


def _decode(data: str) -> str:
    """
    Decode Gmail's base64url-encoded content to a plain string.

    Gmail uses base64url encoding (RFC 4648):
    - Uses - and _ instead of + and /
    - The += "==" pads to a multiple of 4 (required by the spec)
    """
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning("Base64 decode failed: %s", e)
        return ""


def _strip_html(html: str) -> str:
    """Remove all HTML tags and return clean readable text."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    # Remove script and style blocks entirely — we don't want their content
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    return soup.get_text(separator="\n").strip()
