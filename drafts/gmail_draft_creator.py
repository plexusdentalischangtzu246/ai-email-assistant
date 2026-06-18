# drafts/gmail_draft_creator.py
#
# WHY THIS FILE EXISTS:
# An alternative to auto-sending replies.
# Instead of sending immediately, this saves the reply as a Gmail Draft
# so you can review it in Gmail before deciding to send.
#
# WHEN TO USE THIS vs gmail_sender.py:
# Use draft_creator when: the email is sensitive, you're testing, or you
# want a "human in the loop" before any reply goes out.
# Use gmail_sender when: you trust the AI enough to send automatically.
#
# In main.py you choose which one to call based on category or config.

import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from auth.gmail_auth import get_gmail_service
from utils.logger import get_logger

logger = get_logger(__name__)


def create_draft(
    to_email: str,
    subject: str,
    body: str,
    thread_id: str = "",
) -> dict:
    """
    Save an email reply as a Gmail Draft (does NOT send it).

    Args:
        to_email:  Recipient address
        subject:   Subject line
        body:      Reply body text
        thread_id: Gmail thread ID (keeps draft in the same conversation)

    Returns:
        Gmail draft object dict with 'id' field
    """

    service = get_gmail_service()

    message = MIMEMultipart()
    message["to"]      = to_email
    message["subject"] = subject if subject.startswith("Re:") else f"Re: {subject}"
    message.attach(MIMEText(body, "plain", "utf-8"))

    raw_encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    draft_body = {"message": {"raw": raw_encoded}}
    if thread_id:
        draft_body["message"]["threadId"] = thread_id

    draft = service.users().drafts().create(
        userId="me",
        body=draft_body,
    ).execute()

    logger.info("Draft created [ID: %s] → %s | %s", draft["id"], to_email, subject[:40])
    return draft
