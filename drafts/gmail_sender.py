# drafts/gmail_sender.py
#
# WHY THIS FILE EXISTS:
# Sends an email reply via the Gmail API.
# This is the final step in the auto-reply pipeline.
#
# FIX FROM YOUR ORIGINAL CODE:
# 1. Your version split sender email with string operations INSIDE main.py:
#       if "<" in sender_email:
#           sender_email = sender_email.split("<")[1].replace(">","")
#    That's fragile and belongs here, not in the orchestrator.
#    Fixed: parser.py now extracts sender_email cleanly, and this
#    file validates it before sending.
#
# 2. No safety gates. Your version replied to EVERYTHING including
#    spam, no-reply addresses, and promotions.
#    Fixed: safe_send_reply() checks category and noreply patterns
#    BEFORE sending anything.
#
# 3. No thread linking. Replies weren't attached to the original thread.
#    Fixed: pass thread_id so the reply shows up in the same conversation.

import base64
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from auth.gmail_auth import get_gmail_service
from utils.logger import get_logger

logger = get_logger(__name__)

# Categories that should NEVER receive auto-replies.
# We never reply to spam (could confirm your address to spammers)
# or promotions (you'd be replying to marketing bots).
_BLOCKED_CATEGORIES = {"SPAM", "PROMOTION", "SOCIAL"}

# Patterns that indicate automated/no-reply senders.
# Replying to these is pointless — no human reads them.
_NOREPLY_PATTERNS = [
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster", "bounce",
]


def send_email(
    to_email: str,
    subject: str,
    body: str,
    thread_id: str = "",
) -> dict:
    """
    Send an email via Gmail API.

    Args:
        to_email:  Recipient address (must be clean email, not "Name <email>")
        subject:   Subject line
        body:      Plain text body
        thread_id: Gmail thread ID — links this reply to an existing conversation

    Returns:
        Sent message dict from Gmail API (contains the new message's 'id')

    Raises:
        ValueError:  if to_email is invalid
        HttpError:   if Gmail API rejects the request
    """

    if not to_email or "@" not in to_email:
        raise ValueError(f"Invalid email address: '{to_email}'")

    service = get_gmail_service()

    # Build MIME message
    message = MIMEMultipart()
    message["to"]      = to_email
    message["subject"] = subject if subject.startswith("Re:") else f"Re: {subject}"

    message.attach(MIMEText(body, "plain", "utf-8"))

    # Encode to base64url — required by Gmail API
    raw_encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    send_body = {"raw": raw_encoded}
    if thread_id:
        send_body["threadId"] = thread_id  # Links to original conversation

    sent = service.users().messages().send(
        userId="me",
        body=send_body,
    ).execute()

    logger.info("Email sent → %s | Re: %s [Gmail ID: %s]", to_email, subject[:40], sent["id"])
    return sent


def safe_send_reply(
    parsed_email: dict,
    reply_body: str,
    category: str,
) -> tuple[bool, str]:
    """
    Send a reply with built-in safety checks.

    This is what main.py should call — NOT send_email() directly.
    All safety checks live here so they're never accidentally bypassed.

    Safety Gate 1: Category — never reply to SPAM, PROMOTION, SOCIAL
    Safety Gate 2: Email validation — reject malformed addresses
    Safety Gate 3: No-reply detection — don't reply to automated senders

    Returns:
        (True, gmail_message_id)  if sent successfully
        (False, reason_string)    if blocked or failed
    """

    to_email  = parsed_email.get("sender_email", "")
    subject   = parsed_email.get("subject", "")
    thread_id = parsed_email.get("thread_id", "")

    # ── Gate 1: Category check ────────────────────────────────────────────────
    if category in _BLOCKED_CATEGORIES:
        logger.info("Reply blocked — category '%s' is not eligible", category)
        return False, f"blocked_category:{category}"

    # ── Gate 2: Email address validation ─────────────────────────────────────
    if not to_email or "@" not in to_email:
        logger.warning("Reply blocked — invalid sender email: '%s'", to_email)
        return False, "invalid_email"

    # ── Gate 3: No-reply address detection ───────────────────────────────────
    if any(pattern in to_email.lower() for pattern in _NOREPLY_PATTERNS):
        logger.info("Reply blocked — detected no-reply address: %s", to_email)
        return False, "noreply_address"

    # ── Send ──────────────────────────────────────────────────────────────────
    try:
        sent = send_email(
            to_email=to_email,
            subject=subject,
            body=reply_body,
            thread_id=thread_id,
        )
        return True, sent["id"]

    except Exception as e:
        logger.error("Failed to send reply to %s: %s", to_email, e)
        return False, str(e)
