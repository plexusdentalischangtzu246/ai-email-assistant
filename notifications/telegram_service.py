# notifications/telegram_service.py
#
# UPDATED: Added notify_sensitive_email() — a special alert function
# for sensitive emails that:
#   1. Shows the sensitivity type prominently
#   2. NEVER shows the actual OTP/code (uses masked version only)
#   3. Shows a clear "DO NOT SHARE" warning
#   4. Has a different visual style from regular email notifications
#      so you immediately know it's a security-relevant email

import os
import requests
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
_API_URL   = f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage"
_MAX_LEN   = 4000


def send_message(text: str) -> bool:
    """Send a message. Returns True/False, never raises."""
    if not _BOT_TOKEN or not _CHAT_ID:
        logger.debug("Telegram not configured — skipping")
        return False

    if len(text) > _MAX_LEN:
        text = text[:_MAX_LEN] + "\n...[truncated]"

    try:
        resp = requests.post(
            _API_URL,
            json={"chat_id": _CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
        logger.debug("Telegram sent")
        return True
    except requests.exceptions.Timeout:
        logger.warning("Telegram timed out")
        return False
    except requests.exceptions.RequestException as e:
        logger.warning("Telegram failed: %s", e)
        return False


def notify_new_email(parsed: dict, category: str, priority: str) -> bool:
    """Standard notification for a regular (non-sensitive) email."""
    priority_line = priority.replace("\n", "  |  ")
    message = (
        f"📩 <b>NEW EMAIL</b>\n\n"
        f"👤 <b>From:</b> {parsed.get('sender_email', '?')}\n"
        f"📝 <b>Subject:</b> {parsed.get('subject', '?')}\n"
        f"📂 <b>Category:</b> {category}\n"
        f"⚡ <b>Priority:</b> {priority_line}\n\n"
        f"<i>{parsed.get('snippet', '')[:300]}</i>"
    )
    return send_message(message)


def notify_sensitive_email(
    parsed: dict,
    sensitive_type: str,
    priority: str,
    detected_by: str = "regex",
) -> bool:
    """
    Special high-visibility alert for sensitive emails.

    SECURITY RULES enforced here:
    - The actual email body is NEVER included in this notification
    - Only the subject and sender are shown
    - A clear warning is shown not to share any codes
    - The sensitivity type is shown prominently
    - Auto-reply disabled notice is included

    This way even if someone sees your Telegram notification on a
    locked screen or in a screenshot, they cannot steal your OTP.
    """

    # Map sensitive types to emoji + label for the notification
    type_display = {
        "OTP":             "🔑 One-Time Password (OTP)",
        "BANK_ALERT":      "🏦 Bank Transaction Alert",
        "PASSWORD_RESET":  "🔓 Password Reset",
        "LOGIN_ALERT":     "🚨 Login / Sign-in Alert",
        "KYC":             "📋 KYC / Identity Verification",
        "CARD_ALERT":      "💳 Card Transaction Alert",
        "FRAUD_ALERT":     "⚠️ Fraud / Suspicious Activity",
        "ACCOUNT_ALERT":   "🔒 Account Security Alert",
        "LEGAL":           "⚖️ Legal / Compliance Notice",
        "FINANCIAL":       "💰 Financial Document",
        "OTHER_SENSITIVE": "🔐 Sensitive Content",
    }

    display = type_display.get(sensitive_type, "🔐 Sensitive Email")
    priority_line = priority.replace("\n", "  |  ")
    detection_note = "auto-detected" if detected_by == "regex" else "AI-detected"

    message = (
        f"🔐 <b>SENSITIVE EMAIL RECEIVED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Type:</b> {display}\n"
        f"👤 <b>From:</b> {parsed.get('sender_email', '?')}\n"
        f"📝 <b>Subject:</b> {parsed.get('subject', '?')}\n"
        f"⚡ <b>Priority:</b> {priority_line}\n"
        f"🔍 <b>Detection:</b> {detection_note}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <b>Codes/numbers hidden for security</b>\n"
        f"🚫 <b>Auto-reply DISABLED</b>\n"
        f"📱 Open Gmail to view full content\n"
        f"🔕 <b>Do NOT share OTPs with anyone</b>"
    )
    return send_message(message)


def notify_reply_sent(to_email: str, subject: str, reply_preview: str) -> bool:
    """Notification that an auto-reply was sent."""
    message = (
        f"✅ <b>AUTO-REPLY SENT</b>\n\n"
        f"📨 <b>To:</b> {to_email}\n"
        f"📝 <b>Re:</b> {subject}\n\n"
        f"<b>Reply:</b>\n<i>{reply_preview[:400]}</i>"
    )
    return send_message(message)


def notify_error(context: str, error: str) -> bool:
    """Alert when something important fails."""
    message = (
        f"❌ <b>PIPELINE ERROR</b>\n\n"
        f"📍 <b>Where:</b> {context}\n"
        f"💥 <b>Error:</b> {str(error)[:400]}"
    )
    return send_message(message)


if __name__ == "__main__":
    ok = send_message("🚀 AI Email Assistant — Telegram test OK!")
    print("✅ Sent!" if ok else "❌ Failed — check .env")
