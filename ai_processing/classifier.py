# ai_processing/classifier.py
#
# UPDATED: Added "SENSITIVE" as a valid category.
# Sensitive emails (OTP, bank alerts, password resets, login alerts, etc.)
# now get their own category so the dashboard, DB, and pipeline can treat
# them differently from regular IMPORTANT emails.
#
# Key difference from IMPORTANT:
#   IMPORTANT  → might get an auto-reply
#   SENSITIVE  → NEVER gets an auto-reply, codes are masked, high-priority alert sent
#
# The classifier no longer needs to detect sensitive content itself —
# sensitive_detector.py does that with regex + LLM.
# If sensitive_detector marks an email as sensitive, main.py overrides
# whatever this classifier returns with "SENSITIVE".
# This classifier still runs for ALL emails so we have a fallback category.

import os
from openai import OpenAI
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

_client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

_MODEL = "openai/gpt-4o-mini"
_MAX_BODY_CHARS = 2000

# SENSITIVE is intentionally NOT in this set.
# The classifier never returns SENSITIVE — that comes from sensitive_detector.py.
# This separation keeps each module focused on ONE job.
VALID_CATEGORIES = {"IMPORTANT", "PROMOTION", "SOCIAL", "SPAM", "UPDATES"}


def classify_email(subject: str, body: str) -> str:
    """
    Classify an email into one of 5 categories.

    NOTE: This function does NOT detect sensitive emails.
    Call analyze_sensitive() from sensitive_detector.py first.
    If that returns is_sensitive=True, override this result with "SENSITIVE".

    Returns one of: IMPORTANT | PROMOTION | SOCIAL | SPAM | UPDATES
    Always returns a valid category string, never raw LLM output.
    """

    prompt = f"""Classify this email into EXACTLY ONE of these categories:
IMPORTANT | PROMOTION | SOCIAL | SPAM | UPDATES

Definitions:
- IMPORTANT: Work emails, tasks, deadlines, client messages, anything requiring action
- PROMOTION: Marketing, sales offers, discounts, product announcements
- SOCIAL: Social media notifications, newsletters, community updates
- SPAM: Unsolicited, suspicious, phishing attempts, bulk irrelevant mail
- UPDATES: Receipts, shipping notifications, account alerts, service updates

SUBJECT: {subject}
BODY: {body[:_MAX_BODY_CHARS]}

Return ONLY the category name. Nothing else."""

    logger.debug("Classifying: %s", subject[:50])

    try:
        response = _client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0.1,
        )

        raw = response.choices[0].message.content.strip().upper()

        if raw in VALID_CATEGORIES:
            logger.debug("Category: %s", raw)
            return raw

        for cat in VALID_CATEGORIES:
            if cat in raw:
                logger.warning("Partial match: '%s' → '%s'", raw, cat)
                return cat

        logger.warning("Unrecognized category '%s' — defaulting to UPDATES", raw)
        return "UPDATES"

    except Exception as e:
        logger.error("Classification failed: %s", e)
        return "UPDATES"
