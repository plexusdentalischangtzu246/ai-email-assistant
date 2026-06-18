# main.py
#
# UPDATED: Human Decision Detection Layer integrated.
#
# Processing order:
#   1. Fetch + parse (unchanged)
#   2. Deduplication check (unchanged)
#   3. *** SENSITIVE DETECTION *** (runs FIRST before anything else)
#       - If sensitive: mask body, override category to "SENSITIVE",
#         skip auto-reply, send special Telegram alert
#       - If not sensitive: continue normal pipeline
#   4. AI Summary (uses masked body for sensitive emails)
#   5. Classify (result overridden to "SENSITIVE" if detector fired)
#   6. Priority
#   7. Telegram notification (different function for sensitive vs normal)
#   8. Auto-reply — NOW with Human Decision Detection:
#       - Runs detect_decision() AFTER generating draft, BEFORE sending
#       - HUMAN_DECISION_REQUIRED → block send, Telegram approval (PENDING_APPROVAL)
#       - AUTO_REPLY_ALLOWED → existing send flow (AUTO_SENT)
#       - SENSITIVE → always blocked
#   9. Save to DB (includes is_sensitive, sensitive_type, reply_status)
#
# WHY SENSITIVE DETECTION RUNS FIRST:
# We need to mask the body BEFORE passing it to the LLM summarizer.
# If we summarize first, the LLM might echo the OTP in the summary.
# Masking first means the summary also contains [CODE MASKED] instead
# of the real code — safe to store in DB and show on dashboard.

import os
import sys
from dotenv import load_dotenv

load_dotenv()

from utils.logger import get_logger
from storage.data_store import initialize, is_processed, store_email
from email_engine.fetcher import fetch_emails
from email_engine.parser import parse_email
from ai_processing.sensitive_detector import analyze_sensitive
from ai_processing.summarizer import summarize_email
from ai_processing.classifier import classify_email
from ai_processing.priority_analyzer import analyze_priority
from ai_processing.reply_generator import generate_reply
from ai_processing.decision_detector import (
    detect_decision,
    HUMAN_DECISION_REQUIRED,
    AUTO_REPLY_ALLOWED,
)
from notifications.telegram_service import (
    notify_new_email,
    notify_sensitive_email,
    notify_reply_sent,
    notify_error,
)
from notifications.telegram_approval import notify_human_decision_required
from drafts.gmail_sender import safe_send_reply

logger = get_logger(__name__)

MAX_EMAILS      = int(os.getenv("MAX_EMAILS_PER_FETCH", 5))
GMAIL_QUERY     = os.getenv("GMAIL_FETCH_QUERY", "is:unread")
AUTO_REPLY_CATS = set(os.getenv("AUTO_REPLY_CATEGORIES", "IMPORTANT").split(","))
REPLY_TONE      = os.getenv("REPLY_TONE", "professional")


def process_email(parsed: dict) -> bool:
    """
    Run one parsed email through the complete pipeline.

    Returns True if the email was saved successfully, False otherwise.
    """

    subject = parsed["subject"]
    body    = parsed["body"]

    logger.info("── Processing: %s", subject[:60])

    # ══════════════════════════════════════════════════════════════
    # STEP 1 — SENSITIVE DETECTION (must run before everything else)
    # ══════════════════════════════════════════════════════════════
    sensitive_result = None
    is_sensitive     = False
    sensitive_type   = None

    try:
        sensitive_result = analyze_sensitive(parsed)
        is_sensitive     = sensitive_result.is_sensitive
        sensitive_type   = sensitive_result.sensitive_type

        if is_sensitive:
            logger.info(
                "  🔐 SENSITIVE: type=%s detected_by=%s",
                sensitive_type, sensitive_result.detected_by
            )
            # Replace the body in our working copy with the masked version
            # so ALL downstream steps (summarizer, Telegram) use safe text
            body = sensitive_result.masked_body
            parsed = {**parsed, "body": body}  # non-destructive copy

    except Exception as e:
        logger.error("  ✗ Sensitive detection failed: %s", e)
        # On detection failure, treat as non-sensitive and continue
        is_sensitive = False

    # ══════════════════════════════════════════════════════════════
    # STEP 2 — AI SUMMARY
    # Uses masked body if sensitive — safe to store
    # ══════════════════════════════════════════════════════════════
    summary = ""
    try:
        summary = summarize_email(parsed)
        logger.info("  ✓ Summary generated")
    except Exception as e:
        logger.error("  ✗ Summary failed: %s", e)

    # ══════════════════════════════════════════════════════════════
    # STEP 3 — CLASSIFY
    # Override with "SENSITIVE" if detector fired
    # ══════════════════════════════════════════════════════════════
    category = "UPDATES"
    if is_sensitive:
        # Sensitive overrides everything — it gets its own category
        category = "SENSITIVE"
        logger.info("  ✓ Category: SENSITIVE (overridden by detector)")
    else:
        try:
            category = classify_email(subject, body)
            logger.info("  ✓ Category: %s", category)
        except Exception as e:
            logger.error("  ✗ Classification failed: %s", e)

    # ══════════════════════════════════════════════════════════════
    # STEP 4 — PRIORITY
    # ══════════════════════════════════════════════════════════════
    priority = ""
    try:
        priority = analyze_priority(subject, body)
        # Force HIGH urgency for sensitive emails regardless of LLM score
        if is_sensitive and "HIGH" not in priority:
            priority = "PRIORITY: 9/10\nURGENCY: HIGH\nACTION: YES"
            logger.info("  ✓ Priority forced HIGH (sensitive email)")
        else:
            logger.info("  ✓ Priority: %s", priority.replace("\n", " | "))
    except Exception as e:
        logger.error("  ✗ Priority failed: %s", e)
        if is_sensitive:
            priority = "PRIORITY: 9/10\nURGENCY: HIGH\nACTION: YES"

    # ══════════════════════════════════════════════════════════════
    # STEP 5 — TELEGRAM NOTIFICATION
    # Different function for sensitive vs normal emails
    # ══════════════════════════════════════════════════════════════
    try:
        if is_sensitive and sensitive_result:
            notify_sensitive_email(
                parsed=parsed,
                sensitive_type=sensitive_type,
                priority=priority,
                detected_by=sensitive_result.detected_by,
            )
            logger.info("  ✓ Sensitive alert sent to Telegram")
        else:
            notify_new_email(parsed, category, priority)
            logger.info("  ✓ Telegram notification sent")
    except Exception as e:
        logger.warning("  ✗ Telegram failed (non-critical): %s", e)

    # ══════════════════════════════════════════════════════════════
    # STEP 6 — AUTO-REPLY
    # BLOCKED for all sensitive emails — unconditionally.
    # For IMPORTANT emails: Human Decision Detector runs AFTER draft
    # generation but BEFORE sending. It determines whether this email
    # can be auto-replied or requires the user's personal decision.
    # ══════════════════════════════════════════════════════════════
    reply_draft  = ""
    sent_reply   = False
    reply_status = None

    if is_sensitive:
        logger.info("  🚫 Auto-reply BLOCKED — sensitive email")

    elif category in AUTO_REPLY_CATS:
        try:
            reply_draft = generate_reply(
                sender=parsed["sender"],
                subject=subject,
                body=body,
                tone=REPLY_TONE,
            )
            logger.info("  ✓ Reply draft generated")

            # ════════════════════════════════════════════════════════════
            # HUMAN DECISION DETECTION — runs AFTER draft generation
            # but BEFORE sending. Intercepts emails requiring personal
            # knowledge, availability, commitments, or opinions.
            # ════════════════════════════════════════════════════════════
            decision = detect_decision(parsed, subject, body)

            if decision.decision == HUMAN_DECISION_REQUIRED:
                # ——— BLOCK AUTO-SEND — Telegram approval required ———
                logger.info(
                    "  🧠 HUMAN DECISION REQUIRED [%s] — blocking auto-reply",
                    decision.detected_by
                )
                try:
                    notify_human_decision_required(
                        parsed=parsed,
                        reply_draft=reply_draft,
                        reason=decision.reason,
                        email_id=parsed["id"],
                    )
                    logger.info("  ✓ Telegram approval request sent")
                except Exception as e:
                    logger.warning("  ✗ Telegram approval notification failed: %s", e)

                sent_reply   = False
                reply_status = "PENDING_APPROVAL"

            else:
                # ——— AUTO_REPLY_ALLOWED — existing send flow ———
                logger.info("  ✓ AUTO_REPLY_ALLOWED — proceeding to send")

                sent_reply, result = safe_send_reply(
                    parsed_email=parsed,
                    reply_body=reply_draft,
                    category=category,
                )

                if sent_reply:
                    reply_status = "AUTO_SENT"
                    logger.info("  ✓ Auto-reply sent [%s]", result)
                    notify_reply_sent(parsed["sender_email"], subject, reply_draft)
                else:
                    logger.info("  ↩ Reply not sent: %s", result)

        except Exception as e:
            logger.error("  ✗ Auto-reply failed: %s", e)
            notify_error("auto-reply", str(e))

    # ══════════════════════════════════════════════════════════════
    # STEP 7 — SAVE TO DATABASE
    # Stores masked body for sensitive emails
    # ══════════════════════════════════════════════════════════════
    try:
        store_email(
            parsed_email=parsed,
            summary=summary,
            category=category,
            priority=priority,
            reply_draft=reply_draft,
            sent_reply=sent_reply,
            is_sensitive=is_sensitive,
            sensitive_type=sensitive_type,
            reply_status=reply_status,
        )
        logger.info("  ✓ Saved to database")
        return True

    except Exception as e:
        logger.error("  ✗ Database save failed: %s", e)
        return False


def run() -> None:
    """Execute one complete email processing cycle."""

    logger.info("=" * 60)
    logger.info("AI EMAIL ASSISTANT — Starting")
    logger.info("=" * 60)

    initialize()

    logger.info("Fetching up to %d emails — query: '%s'", MAX_EMAILS, GMAIL_QUERY)
    try:
        raw_emails = fetch_emails(max_results=MAX_EMAILS, query=GMAIL_QUERY)
    except Exception as e:
        logger.critical("Failed to fetch emails: %s", e)
        sys.exit(1)

    if not raw_emails:
        logger.info("No emails to process.")
        return

    logger.info("Found %d email(s)", len(raw_emails))

    processed = skipped = failed = 0

    for raw in raw_emails:
        try:
            parsed = parse_email(raw)
        except Exception as e:
            logger.error("Parse failed: %s", e)
            failed += 1
            continue

        if is_processed(parsed["id"]):
            logger.info("⏭  Already processed: %s", parsed["subject"][:50])
            skipped += 1
            continue

        ok = process_email(parsed)
        if ok:
            processed += 1
        else:
            failed += 1

    logger.info("=" * 60)
    logger.info("Done — Processed: %d | Skipped: %d | Failed: %d",
                processed, skipped, failed)
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
