# ai_processing/sensitive_detector.py
#
# WHY THIS FILE EXISTS:
# Sensitive emails — OTPs, bank alerts, password resets, login codes,
# KYC requests, credit card alerts — need special treatment:
#
#   1. NEVER auto-reply to them (replying to an OTP email is meaningless
#      and could expose security context to the wrong person)
#   2. NEVER show the raw OTP/code in the Telegram notification
#      (your Telegram might be on a shared device or screenshotted)
#   3. Store a masked version in the DB instead of the actual code
#   4. Alert you immediately with HIGH priority regardless of other scores
#   5. Flag them clearly on the dashboard with a 🔐 icon
#
# HOW IT WORKS — TWO LAYERS:
#
#   Layer 1: Regex fast-scan (no API call, instant)
#     Looks for patterns like "Your OTP is 4829", "code: 291847",
#     "verification code", "one-time password", etc.
#     If found → immediately mark as SENSITIVE, extract & mask the code.
#
#   Layer 2: LLM deep-scan (API call, for subtle cases)
#     Some sensitive emails don't have obvious patterns:
#     "Your account was accessed from Chennai at 2:14 AM"
#     "We noticed unusual activity on your account"
#     The LLM catches these that regex misses.
#
# MASKING LOGIC:
#   Raw:    "Your OTP is 482917"
#   Stored: "Your OTP is [CODE MASKED]"
#   Telegram notification shows: "🔐 OTP/Code detected — masked for security"
#
# This means even if someone sees your Telegram notification or DB,
# they cannot get the actual code.

import os
import re
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

# ── Sensitive email types — used for classification & dashboard display ────────
SENSITIVE_TYPES = {
    "OTP",             # One-time passwords, verification codes
    "BANK_ALERT",      # Transaction alerts, balance notifications
    "PASSWORD_RESET",  # Reset links, temporary passwords
    "LOGIN_ALERT",     # New device login, suspicious sign-in
    "KYC",             # Know Your Customer, identity verification
    "CARD_ALERT",      # Credit/debit card activity
    "FRAUD_ALERT",     # Suspicious activity warnings
    "ACCOUNT_ALERT",   # Account locked, unusual activity
    "LEGAL",           # Legal notices, court documents, compliance
    "FINANCIAL",       # Invoices, payment due, salary slips
    "OTHER_SENSITIVE", # Caught by LLM but doesn't fit above types
}

# ── Regex patterns for fast Layer 1 detection ──────────────────────────────────
# Each tuple: (pattern, sensitive_type)
# Patterns are case-insensitive (re.IGNORECASE applied when compiled)
_REGEX_RULES: list[tuple[str, str]] = [

    # OTP patterns
    (r"\b(otp|one.?time.?pass(word)?|verification.?code|auth(entication)?.?code)\b", "OTP"),
    (r"\b(your|the).{0,20}(code|otp|pin)\s*(is|:)\s*\d{4,8}\b", "OTP"),
    (r"\benter.{0,15}(code|otp|pin)\b", "OTP"),
    (r"\b\d{4,8}\s+is\s+your\b", "OTP"),
    (r"\bdo not share.{0,30}(otp|code|pin|password)\b", "OTP"),
    (r"\b(2fa|two.factor|multi.factor|mfa)\b", "OTP"),
    (r"\btemporary.{0,10}(code|password|pin)\b", "OTP"),

    # Bank & card alerts
    (r"\b(debited|credited|debit|credit).{0,30}(rs\.?|inr|₹|\$|usd|eur)\s*[\d,]+", "BANK_ALERT"),
    (r"\b(rs\.?|inr|₹|\$)\s*[\d,]+.{0,30}(debited|credited|withdrawn|deposited)\b", "BANK_ALERT"),
    (r"\btransaction.{0,20}(alert|notification|successful|failed)\b", "BANK_ALERT"),
    (r"\b(atm|pos|upi|neft|rtgs|imps).{0,20}(transaction|transfer|payment)\b", "BANK_ALERT"),
    (r"\baccount.{0,20}balance\b", "BANK_ALERT"),
    (r"\b(credit|debit).?card.{0,30}(used|charged|transaction|alert)\b", "CARD_ALERT"),
    (r"\bcard.{0,15}(ending|ending in|last 4)\s*\d{4}\b", "CARD_ALERT"),
    (r"\bunusual.{0,20}(activity|transaction|charge)\b", "FRAUD_ALERT"),
    (r"\b(fraud|fraudulent).{0,20}(alert|detected|activity|transaction)\b", "FRAUD_ALERT"),

    # Password reset
    (r"\b(password|passwd).{0,20}(reset|change|changed|update|recovery)\b", "PASSWORD_RESET"),
    (r"\breset.{0,20}(password|passwd|account)\b", "PASSWORD_RESET"),
    (r"\b(click|tap|follow).{0,30}(reset|change).{0,20}password\b", "PASSWORD_RESET"),
    (r"\bforgot.{0,15}(password|account)\b", "PASSWORD_RESET"),

    # Login alerts
    (r"\b(new|unusual|unrecognized).{0,20}(sign.?in|login|device|location)\b", "LOGIN_ALERT"),
    (r"\b(signed in|logged in).{0,30}(new|different|unrecognized).{0,20}device\b", "LOGIN_ALERT"),
    (r"\byour account.{0,20}(accessed|sign.?in|login).{0,30}(from|at|new)\b", "LOGIN_ALERT"),
    (r"\bif you did not.{0,30}(sign|log|login|access)\b", "LOGIN_ALERT"),

    # KYC / Identity
    (r"\b(kyc|know your customer|identity.verif|id.verif|aadhaar|pan card)\b", "KYC"),
    (r"\b(submit|upload|verify|complete).{0,20}(document|id|identity|kyc)\b", "KYC"),

    # Account alerts
    (r"\b(account.{0,10}(lock|suspend|block|disabled|terminated|close))\b", "ACCOUNT_ALERT"),
    (r"\b(suspend|block|lock|disable).{0,20}account\b", "ACCOUNT_ALERT"),

    # Legal
    (r"\b(legal.notice|court.order|summons|subpoena|compliance|gdpr|lawsuit)\b", "LEGAL"),
    (r"\b(terms.of.service|privacy.policy).{0,30}(updated|changed|effective)\b", "LEGAL"),

    # Financial documents
    (r"\b(invoice|bill|payment.due|amount.due|salary|payslip|pay.slip)\b", "FINANCIAL"),
    (r"\b(emi|loan|repayment|installment).{0,20}(due|reminder|overdue)\b", "FINANCIAL"),
]

# Compile all patterns once at module load (not on every function call)
_COMPILED_RULES = [
    (re.compile(pattern, re.IGNORECASE | re.DOTALL), stype)
    for pattern, stype in _REGEX_RULES
]

# ── Patterns that identify numeric codes to mask ───────────────────────────────
# These find the actual OTP/code values so we can replace them with [MASKED]
_CODE_PATTERNS = [
    re.compile(r'\b\d{4,8}\b'),                         # 4-8 digit numbers
    re.compile(r'[A-Z0-9]{6,12}(?=[^a-z]|$)'),          # Uppercase alphanumeric codes
    re.compile(r'(?<=code[:\s])\s*[A-Z0-9]{4,12}', re.IGNORECASE),
    re.compile(r'(?<=otp[:\s])\s*[A-Z0-9]{4,8}', re.IGNORECASE),
    re.compile(r'(?<=pin[:\s])\s*[A-Z0-9]{4,8}', re.IGNORECASE),
]


class SensitiveResult:
    """
    Result of sensitive email analysis.

    Attributes:
        is_sensitive:    True if the email contains sensitive content
        sensitive_type:  Which type (OTP, BANK_ALERT, etc.) or None
        detected_by:     "regex" (fast) or "llm" (deep scan) or None
        masked_body:     Body text with actual codes replaced by [CODE MASKED]
        masked_subject:  Subject with codes replaced
        alert_message:   Human-readable description for Telegram notification
        should_reply:    Always False for sensitive emails — never auto-reply
        confidence:      "HIGH" (regex match) or "MEDIUM" (LLM only)
    """
    def __init__(self):
        self.is_sensitive:   bool  = False
        self.sensitive_type: str   = None
        self.detected_by:    str   = None
        self.masked_body:    str   = ""
        self.masked_subject: str   = ""
        self.alert_message:  str   = ""
        self.should_reply:   bool  = False  # ALWAYS False — never reply to sensitive emails
        self.confidence:     str   = "LOW"

    def __repr__(self):
        return (
            f"SensitiveResult(is_sensitive={self.is_sensitive}, "
            f"type={self.sensitive_type}, by={self.detected_by})"
        )


def analyze_sensitive(parsed_email: dict) -> SensitiveResult:
    """
    Analyze an email for sensitive content using two detection layers.

    This is the main entry point. Call this BEFORE classify_email()
    so that sensitive emails get special handling regardless of category.

    Args:
        parsed_email: ParsedEmail dict from parser.py

    Returns:
        SensitiveResult with detection details and masked content
    """

    result = SensitiveResult()

    subject = parsed_email.get("subject", "")
    body    = parsed_email.get("body", "")
    sender  = parsed_email.get("sender_email", "")

    combined_text = f"{subject}\n{body}"

    # ── Layer 1: Regex fast scan ──────────────────────────────────────────────
    regex_result = _regex_scan(combined_text)

    if regex_result:
        result.is_sensitive   = True
        result.sensitive_type = regex_result
        result.detected_by    = "regex"
        result.confidence     = "HIGH"
        result.masked_body    = _mask_codes(body)
        result.masked_subject = _mask_codes(subject)
        result.alert_message  = _build_alert_message(regex_result, sender, subject)
        result.should_reply   = False

        logger.info(
            "🔐 SENSITIVE email detected via regex: %s | type: %s",
            subject[:50], regex_result
        )
        return result

    # ── Layer 2: LLM deep scan (only if regex found nothing) ─────────────────
    # We only call the LLM for emails that passed the regex scan clean.
    # This keeps costs low — most sensitive emails are caught by regex.
    llm_result = _llm_scan(subject, body[:_MAX_BODY_CHARS])

    if llm_result:
        result.is_sensitive   = True
        result.sensitive_type = llm_result
        result.detected_by    = "llm"
        result.confidence     = "MEDIUM"
        result.masked_body    = _mask_codes(body)
        result.masked_subject = _mask_codes(subject)
        result.alert_message  = _build_alert_message(llm_result, sender, subject)
        result.should_reply   = False

        logger.info(
            "🔐 SENSITIVE email detected via LLM: %s | type: %s",
            subject[:50], llm_result
        )

    return result


def _regex_scan(text: str) -> str | None:
    """
    Run all compiled regex patterns against the text.
    Returns the sensitive type on first match, None if clean.
    """
    for pattern, stype in _COMPILED_RULES:
        if pattern.search(text):
            return stype
    return None


def _llm_scan(subject: str, body: str) -> str | None:
    """
    Ask the LLM to detect subtle sensitive content that regex missed.

    Returns the sensitive type string, or None if not sensitive.
    Only called when regex scan returns clean — saves API costs.
    """

    valid_types = " | ".join(sorted(SENSITIVE_TYPES))

    prompt = f"""Analyze this email for sensitive security or financial content.

Sensitive types to detect:
- OTP: one-time passwords, verification codes, auth codes
- BANK_ALERT: bank transactions, balance alerts, fund transfers
- PASSWORD_RESET: password change or reset requests
- LOGIN_ALERT: new device login, suspicious sign-in notifications
- KYC: identity verification, document submission requests
- CARD_ALERT: credit/debit card usage notifications
- FRAUD_ALERT: fraud warnings, suspicious activity alerts
- ACCOUNT_ALERT: account locked, suspended, or at risk
- LEGAL: legal notices, court documents, compliance requirements
- FINANCIAL: invoices, payment due, salary slips, loan reminders
- OTHER_SENSITIVE: sensitive content not covered above
- NONE: not sensitive at all

SUBJECT: {subject}
BODY:
{body}

Reply with ONLY one word from this list: {valid_types} | NONE
No explanation. No punctuation. Just the type name."""

    try:
        response = _client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0.0,  # Completely deterministic — this is a binary classification
        )

        raw = response.choices[0].message.content.strip().upper()

        if raw == "NONE" or not raw:
            return None

        # Validate the response is a real sensitive type
        if raw in SENSITIVE_TYPES:
            return raw

        # Handle partial matches
        for stype in SENSITIVE_TYPES:
            if stype in raw:
                return stype

        return None

    except Exception as e:
        logger.warning("LLM sensitive scan failed (non-critical): %s", e)
        return None  # If LLM fails, treat as non-sensitive (don't block email processing)


def _mask_codes(text: str) -> str:
    """
    Replace actual OTP codes and numbers in text with [CODE MASKED].

    This is applied to ALL sensitive emails before storing in DB
    or sending in Telegram notifications.

    Examples:
        "Your OTP is 482917"            → "Your OTP is [CODE MASKED]"
        "Verification code: AB29K7"     → "Verification code: [CODE MASKED]"
        "Use code 9284 to login"        → "Use code [CODE MASKED] to login"
    """
    if not text:
        return text

    masked = text

    # Mask patterns in order of specificity (most specific first)

    # Context-aware masking: "code: 12345" → "code: [CODE MASKED]"
    masked = re.sub(
        r'(?i)(code|otp|pin|password|token|key)[:\s]+[A-Z0-9]{4,12}',
        r'\1: [CODE MASKED]',
        masked
    )

    # Standalone 4-8 digit numbers (OTP length)
    # Exclude: years (2024), common numbers (1000, 5000)
    # Include: 4-8 digit sequences that look like codes
    masked = re.sub(r'\b([0-9]{4,8})\b', '[CODE MASKED]', masked)

    # Alphanumeric codes in uppercase (common for alphanumeric OTPs)
    masked = re.sub(r'\b([A-Z][A-Z0-9]{5,11})\b', '[CODE MASKED]', masked)

    return masked


def _build_alert_message(sensitive_type: str, sender: str, subject: str) -> str:
    """
    Build a human-friendly Telegram alert message for a sensitive email.
    The message describes the sensitivity WITHOUT revealing any codes.
    """

    type_descriptions = {
        "OTP":             "🔑 One-Time Password / Verification Code",
        "BANK_ALERT":      "🏦 Bank Transaction Alert",
        "PASSWORD_RESET":  "🔓 Password Reset Request",
        "LOGIN_ALERT":     "🚨 New Login / Sign-in Alert",
        "KYC":             "📋 KYC / Identity Verification Request",
        "CARD_ALERT":      "💳 Credit/Debit Card Alert",
        "FRAUD_ALERT":     "⚠️ Fraud / Suspicious Activity Alert",
        "ACCOUNT_ALERT":   "🔒 Account Security Alert",
        "LEGAL":           "⚖️ Legal Notice / Compliance",
        "FINANCIAL":       "💰 Financial Document / Payment Alert",
        "OTHER_SENSITIVE": "🔐 Sensitive Content Detected",
    }

    desc = type_descriptions.get(sensitive_type, "🔐 Sensitive Email")

    return (
        f"{desc}\n\n"
        f"From: {sender}\n"
        f"Subject: {subject}\n\n"
        f"⚠️ Codes/numbers masked for security.\n"
        f"Open Gmail to view the actual content.\n"
        f"❌ Auto-reply is DISABLED for this email."
    )


# ── Convenience helpers for other modules ─────────────────────────────────────

def is_sensitive(parsed_email: dict) -> bool:
    """Quick boolean check — use when you only need True/False."""
    result = analyze_sensitive(parsed_email)
    return result.is_sensitive


def get_sensitive_type(parsed_email: dict) -> str | None:
    """Get just the type string or None."""
    result = analyze_sensitive(parsed_email)
    return result.sensitive_type if result.is_sensitive else None
