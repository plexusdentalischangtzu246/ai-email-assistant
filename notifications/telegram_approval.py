# notifications/telegram_approval.py
#
# Human Decision Required — Telegram Approval Workflow
#
# WHY THIS FILE EXISTS:
# When the decision_detector flags an email as HUMAN_DECISION_REQUIRED,
# this module handles the complete Telegram interaction:
#
#   1. Send a structured alert with the AI-generated draft + reason
#   2. Show inline keyboard: [✅ Send Draft] [✏️ Edit Reply] [❌ Ignore]
#   3. Process button callbacks from the user
#      - ✅ Send Draft  → send stored AI draft, mark APPROVED
#      - ✏️ Edit Reply  → ask user to type their reply, format it, preview, confirm
#      - ❌ Ignore      → mark IGNORED, no email sent
#
# HOW TELEGRAM INLINE KEYBOARDS WORK:
#   We use sendMessage with reply_markup.inline_keyboard.
#   When the user taps a button, Telegram sends a callback_query update.
#   monitor.py polls getUpdates to receive these callbacks.
#   handle_callback_query() in this module processes them.
#
# EDIT FLOW STATE:
#   When the user clicks ✏️ Edit Reply, we need to remember which email
#   they are editing when their next text message arrives.
#   State is stored in drafts/pending_edits.json:
#     { "chat_id": { "email_id": "...", "subject": "...", "sender_email": "..." } }

import json
import os
import requests
from datetime import datetime
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")
_API_BASE   = f"https://api.telegram.org/bot{_BOT_TOKEN}"
_MAX_LEN    = 4000

# File to persist "awaiting edited reply" state between monitor cycles
_PENDING_EDITS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "drafts", "pending_edits.json"
)

# Lazy import to avoid circular dependency — these are called AFTER db is ready
def _get_db():
    from database.db_manager import update_reply_status, get_email_by_id
    return update_reply_status, get_email_by_id

def _get_sender():
    from drafts.gmail_sender import safe_send_reply
    return safe_send_reply

def _get_llm():
    from ai_processing.reply_generator import generate_reply
    return generate_reply

def _get_notify():
    from notifications.telegram_service import notify_reply_sent, notify_error
    return notify_reply_sent, notify_error


# ─────────────────────────────────────────────────────────────────────────────
# LOW-LEVEL API HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _post(endpoint: str, payload: dict) -> dict | None:
    """Make a POST request to the Telegram Bot API. Returns JSON or None on error."""
    if not _BOT_TOKEN or not _CHAT_ID:
        logger.debug("Telegram not configured — skipping")
        return None
    try:
        resp = requests.post(
            f"{_API_BASE}/{endpoint}",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        logger.warning("Telegram API timed out (%s)", endpoint)
        return None
    except requests.exceptions.RequestException as e:
        logger.warning("Telegram API error (%s): %s", endpoint, e)
        return None


def _send_text(text: str, reply_markup: dict = None) -> dict | None:
    """
    Send a plain text message to the configured chat.
    Optionally attach an inline keyboard via reply_markup.
    """
    if len(text) > _MAX_LEN:
        text = text[:_MAX_LEN] + "\n...[truncated]"

    payload = {
        "chat_id":    _CHAT_ID,
        "text":       text,
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    return _post("sendMessage", payload)


def _answer_callback(callback_query_id: str, text: str = "") -> None:
    """Acknowledge a callback query to remove the loading spinner."""
    _post("answerCallbackQuery", {
        "callback_query_id": callback_query_id,
        "text": text,
    })


def _edit_message_reply_markup(chat_id: str, message_id: int) -> None:
    """Remove inline keyboard from an existing message (after user acts)."""
    _post("editMessageReplyMarkup", {
        "chat_id":      chat_id,
        "message_id":   message_id,
        "reply_markup": {"inline_keyboard": []},
    })


# ─────────────────────────────────────────────────────────────────────────────
# PENDING EDITS STATE (persisted as JSON)
# ─────────────────────────────────────────────────────────────────────────────

def _load_pending_edits() -> dict:
    """Load the pending edits state file. Returns {} if not found."""
    try:
        os.makedirs(os.path.dirname(_PENDING_EDITS_FILE), exist_ok=True)
        if os.path.exists(_PENDING_EDITS_FILE):
            with open(_PENDING_EDITS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("Could not load pending edits: %s", e)
    return {}


def _save_pending_edits(state: dict) -> None:
    """Persist the pending edits state."""
    try:
        os.makedirs(os.path.dirname(_PENDING_EDITS_FILE), exist_ok=True)
        with open(_PENDING_EDITS_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.warning("Could not save pending edits: %s", e)


def _set_pending_edit(email_id: str, parsed_email: dict) -> None:
    """Mark that we are waiting for the user to type a reply for this email."""
    state = _load_pending_edits()
    state[str(_CHAT_ID)] = {
        "email_id":     email_id,
        "subject":      parsed_email.get("subject", ""),
        "sender":       parsed_email.get("sender", ""),
        "sender_email": parsed_email.get("sender_email", ""),
        "thread_id":    parsed_email.get("thread_id", ""),
        "created_at":   datetime.now().isoformat(),
    }
    _save_pending_edits(state)


def _get_pending_edit() -> dict | None:
    """Get the active pending edit for this chat, or None if none."""
    state = _load_pending_edits()
    return state.get(str(_CHAT_ID))


def _clear_pending_edit() -> None:
    """Clear pending edit state after the user has replied or cancelled."""
    state = _load_pending_edits()
    state.pop(str(_CHAT_ID), None)
    _save_pending_edits(state)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PUBLIC FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def notify_human_decision_required(
    parsed: dict,
    reply_draft: str,
    reason: str,
    email_id: str,
) -> bool:
    """
    Send a Telegram alert for an email that requires human decision.

    Shows:
    - Sender, subject, reason
    - AI-generated draft preview (first 300 chars)
    - Inline keyboard: [✅ Send Draft] [✏️ Edit Reply] [❌ Ignore]

    Returns True if message was sent successfully.
    """
    sender  = parsed.get("sender_email", "?")
    subject = parsed.get("subject", "?")

    draft_preview = reply_draft[:300].strip()
    if len(reply_draft) > 300:
        draft_preview += "..."

    message = (
        f"🧠 <b>HUMAN DECISION REQUIRED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>From:</b> {sender}\n"
        f"📝 <b>Subject:</b> {subject}\n\n"
        f"⚠️ <b>Reason:</b> <i>{reason}</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>Suggested Draft:</b>\n"
        f"<i>{draft_preview}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Choose an action:"
    )

    # Build inline keyboard with callback_data encoding the email_id
    reply_markup = {
        "inline_keyboard": [[
            {"text": "✅ Send Draft",  "callback_data": f"approve_{email_id}"},
            {"text": "✏️ Edit Reply",  "callback_data": f"edit_{email_id}"},
            {"text": "❌ Ignore",      "callback_data": f"ignore_{email_id}"},
        ]]
    }

    result = _send_text(message, reply_markup=reply_markup)
    success = result is not None and result.get("ok", False)

    if success:
        logger.info("🧠 Telegram HUMAN DECISION alert sent for: %s", subject[:50])
    else:
        logger.warning("Failed to send HUMAN DECISION Telegram alert")

    return success


def send_editing_prompt() -> bool:
    """
    Prompt the user to type their reply after clicking ✏️ Edit Reply.
    """
    message = (
        "✏️ <b>Edit Reply</b>\n\n"
        "Please type the reply you want to send.\n\n"
        "<i>Example: \"I am available at 7:30 PM tomorrow.\"</i>\n\n"
        "The AI will convert it to a professional email format and show you a preview."
    )
    result = _send_text(message)
    return result is not None and result.get("ok", False)


def send_reply_preview_with_confirm(
    formatted_reply: str,
    email_id: str,
) -> bool:
    """
    Show the AI-formatted reply preview and ask user to confirm before sending.
    """
    message = (
        f"📋 <b>Reply Preview</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>{formatted_reply[:600]}</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Send this reply?"
    )

    reply_markup = {
        "inline_keyboard": [[
            {"text": "✅ Confirm & Send", "callback_data": f"confirm_edit_{email_id}"},
            {"text": "❌ Cancel",          "callback_data": f"cancel_edit_{email_id}"},
        ]]
    }

    result = _send_text(message, reply_markup=reply_markup)
    return result is not None and result.get("ok", False)


def send_status_message(text: str) -> bool:
    """Send a simple status/info message (no buttons)."""
    result = _send_text(text)
    return result is not None and result.get("ok", False)


# ─────────────────────────────────────────────────────────────────────────────
# CALLBACK HANDLER
# ─────────────────────────────────────────────────────────────────────────────

def handle_callback_query(update: dict) -> None:
    """
    Process a Telegram callback_query update (triggered when user taps an inline button).

    Expected callback_data formats:
        approve_{email_id}        → Send the stored AI draft
        edit_{email_id}           → Ask user to type their reply
        ignore_{email_id}         → Ignore the email, no reply sent
        confirm_edit_{email_id}   → Confirm and send the edited reply
        cancel_edit_{email_id}    → Cancel edit, go back to pending

    This is called from monitor.py whenever a callback_query arrives.
    """
    callback_query    = update.get("callback_query", {})
    callback_id       = callback_query.get("id", "")
    callback_data     = callback_query.get("data", "")
    message           = callback_query.get("message", {})
    message_id        = message.get("message_id")
    chat_id           = str(message.get("chat", {}).get("id", _CHAT_ID))

    if not callback_data:
        return

    logger.info("Telegram callback received: %s", callback_data)

    update_reply_status, get_email_by_id = _get_db()

    # ── ✅ Send Draft ─────────────────────────────────────────────────────────
    if callback_data.startswith("approve_"):
        email_id = callback_data[len("approve_"):]
        _answer_callback(callback_id, "Sending draft...")
        _edit_message_reply_markup(chat_id, message_id)

        email_row = get_email_by_id(email_id)
        if not email_row:
            send_status_message("❌ Email not found in database.")
            return

        reply_draft = email_row.get("reply_draft", "")
        if not reply_draft:
            send_status_message("❌ No draft found for this email.")
            return

        # Reconstruct minimal parsed_email for safe_send_reply
        parsed = {
            "sender_email": email_row.get("sender_email", ""),
            "subject":      email_row.get("subject", ""),
            "thread_id":    email_row.get("thread_id", ""),
        }

        safe_send_reply = _get_sender()
        sent, result = safe_send_reply(
            parsed_email=parsed,
            reply_body=reply_draft,
            category="IMPORTANT",
        )

        if sent:
            update_reply_status(email_id, "APPROVED")
            notify_reply_sent, _ = _get_notify()
            notify_reply_sent(
                parsed["sender_email"],
                parsed["subject"],
                reply_draft,
            )
            send_status_message(
                f"✅ <b>Reply sent!</b>\n\n"
                f"📨 To: {parsed['sender_email']}\n"
                f"📝 Re: {parsed['subject']}\n\n"
                f"Status updated to <b>APPROVED</b>."
            )
            logger.info("✅ Approved draft sent for email_id=%s", email_id)
        else:
            send_status_message(f"❌ <b>Failed to send reply.</b>\nReason: {result}")
            logger.error("Failed to send approved draft: %s", result)

    # ── ✏️ Edit Reply ──────────────────────────────────────────────────────────
    elif callback_data.startswith("edit_"):
        email_id = callback_data[len("edit_"):]
        _answer_callback(callback_id, "Opening editor...")
        _edit_message_reply_markup(chat_id, message_id)

        email_row = get_email_by_id(email_id)
        if not email_row:
            send_status_message("❌ Email not found in database.")
            return

        # Store pending edit state so the next message is treated as the reply
        _set_pending_edit(email_id, {
            "subject":      email_row.get("subject", ""),
            "sender":       email_row.get("sender", ""),
            "sender_email": email_row.get("sender_email", ""),
            "thread_id":    email_row.get("thread_id", ""),
        })

        send_editing_prompt()
        logger.info("✏️ Edit mode activated for email_id=%s", email_id)

    # ── ❌ Ignore ─────────────────────────────────────────────────────────────
    elif callback_data.startswith("ignore_"):
        email_id = callback_data[len("ignore_"):]
        _answer_callback(callback_id, "Ignored.")
        _edit_message_reply_markup(chat_id, message_id)

        update_reply_status(email_id, "IGNORED")
        send_status_message(
            f"❌ <b>Email ignored.</b>\n\n"
            f"No reply will be sent.\n"
            f"Status updated to <b>IGNORED</b>."
        )
        logger.info("❌ Email ignored: email_id=%s", email_id)

    # ── ✅ Confirm edited reply ───────────────────────────────────────────────
    elif callback_data.startswith("confirm_edit_"):
        email_id = callback_data[len("confirm_edit_"):]
        _answer_callback(callback_id, "Sending your reply...")
        _edit_message_reply_markup(chat_id, message_id)

        # The formatted reply was stored in the pending edit state
        pending = _get_pending_edit()
        if not pending or pending.get("email_id") != email_id:
            send_status_message("❌ Could not find pending reply. Please try again.")
            return

        formatted_reply = pending.get("formatted_reply", "")
        if not formatted_reply:
            send_status_message("❌ No reply text found. Please try again.")
            return

        parsed = {
            "sender_email": pending.get("sender_email", ""),
            "subject":      pending.get("subject", ""),
            "thread_id":    pending.get("thread_id", ""),
        }

        safe_send_reply = _get_sender()
        sent, result = safe_send_reply(
            parsed_email=parsed,
            reply_body=formatted_reply,
            category="IMPORTANT",
        )

        if sent:
            update_reply_status(email_id, "APPROVED")
            _clear_pending_edit()
            notify_reply_sent, _ = _get_notify()
            notify_reply_sent(parsed["sender_email"], parsed["subject"], formatted_reply)
            send_status_message(
                f"✅ <b>Your reply has been sent!</b>\n\n"
                f"📨 To: {parsed['sender_email']}\n"
                f"📝 Re: {parsed['subject']}\n\n"
                f"Status updated to <b>APPROVED</b>."
            )
            logger.info("✅ Edited reply sent for email_id=%s", email_id)
        else:
            send_status_message(f"❌ <b>Failed to send reply.</b>\nReason: {result}")
            logger.error("Failed to send edited reply: %s", result)

    # ── ❌ Cancel edited reply ────────────────────────────────────────────────
    elif callback_data.startswith("cancel_edit_"):
        email_id = callback_data[len("cancel_edit_"):]
        _answer_callback(callback_id, "Cancelled.")
        _edit_message_reply_markup(chat_id, message_id)
        _clear_pending_edit()
        send_status_message(
            "❌ Edit cancelled. The email remains in <b>PENDING_APPROVAL</b> status.\n"
            "You can approve or ignore it later via the next Telegram notification."
        )
        logger.info("✏️ Edit cancelled for email_id=%s", email_id)


# ─────────────────────────────────────────────────────────────────────────────
# INCOMING TEXT MESSAGE HANDLER (for edit flow)
# ─────────────────────────────────────────────────────────────────────────────

def handle_incoming_text(update: dict) -> None:
    """
    Handle a plain text message from the user.

    This is only relevant when the user is in "edit mode" (clicked ✏️ Edit Reply).
    In that case, the text they type is treated as their raw reply, which is:
    1. Formatted by the LLM into a professional email
    2. Shown as a preview
    3. Confirmed by the user before sending

    Called from monitor.py for every incoming text message update.
    """
    message = update.get("message", {})
    text    = message.get("text", "").strip()

    if not text or text.startswith("/"):
        return  # Ignore empty messages and bot commands

    pending = _get_pending_edit()
    if not pending:
        return  # No active edit session — ignore

    email_id = pending.get("email_id")
    subject  = pending.get("subject", "")
    sender   = pending.get("sender", "")

    logger.info("📝 Received edit reply for email_id=%s: %s chars", email_id, len(text))

    send_status_message("⏳ Formatting your reply as a professional email...")

    # Format via LLM
    generate_reply = _get_llm()
    try:
        formatted = generate_reply(
            sender=sender,
            subject=subject,
            body=f"[User's intended reply]: {text}",
            tone="professional",
        )
    except Exception as e:
        logger.error("LLM formatting failed: %s", e)
        formatted = text  # Fallback: use raw text

    # Store the formatted reply in pending edit state for the confirm step
    state = _load_pending_edits()
    if str(_CHAT_ID) in state:
        state[str(_CHAT_ID)]["formatted_reply"] = formatted
        _save_pending_edits(state)

    # Show preview with confirm/cancel buttons
    send_reply_preview_with_confirm(formatted, email_id)
