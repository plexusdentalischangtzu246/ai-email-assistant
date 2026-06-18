# ai_processing/decision_detector.py
#
# Human Decision Detection Layer
#
# WHY THIS FILE EXISTS:
# The AI assistant must NEVER make personal decisions on behalf of the user.
# Before sending any auto-reply to an IMPORTANT email, this module determines
# whether the email can be answered with general information (AUTO_REPLY_ALLOWED)
# or requires the user's personal input, availability, commitment, or opinion
# (HUMAN_DECISION_REQUIRED).
#
# EXAMPLES:
#   AUTO_REPLY_ALLOWED:
#     - "Your access request has been approved."
#     - "Meeting link attached below."
#     - "Your report has been submitted successfully."
#     - "Thank you for your application."
#
#   HUMAN_DECISION_REQUIRED:
#     - "Did you complete the project?"
#     - "Can you attend tomorrow at 7:30 PM?"
#     - "Are you available for a call?"
#     - "Do you agree with this proposal?"
#     - "Will you submit before Friday?"
#     - "Can you join our team?"
#
# HOW IT WORKS — TWO LAYERS (mirrors sensitive_detector.py architecture):
#
#   Layer 1: Regex fast-scan (no API call, instant)
#     Detects patterns like direct questions, availability requests,
#     commitment requests, and opinion-seeking phrases.
#     If found → immediately return HUMAN_DECISION_REQUIRED.
#
#   Layer 2: LLM deep-scan (API call, for subtle cases)
#     Some decision-requiring emails don't use obvious patterns.
#     The LLM catches subtle ones that regex misses.
#
# SAFETY CONTRACT:
#   This module NEVER sends any email.
#   It only returns a decision. The caller (main.py) decides what to do.

import os
import re
from dataclasses import dataclass
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

# Decision constants
AUTO_REPLY_ALLOWED       = "AUTO_REPLY_ALLOWED"
HUMAN_DECISION_REQUIRED  = "HUMAN_DECISION_REQUIRED"


@dataclass
class DecisionResult:
    """
    Result of the human decision detection analysis.

    Attributes:
        decision:   AUTO_REPLY_ALLOWED or HUMAN_DECISION_REQUIRED
        reason:     Short human-readable explanation for Telegram notification
        detected_by: "regex" (Layer 1) or "llm" (Layer 2)
        confidence: "HIGH" (regex match) or "MEDIUM" (LLM only)
    """
    decision:    str = AUTO_REPLY_ALLOWED
    reason:      str = ""
    detected_by: str = "none"
    confidence:  str = "HIGH"

    def requires_human(self) -> bool:
        return self.decision == HUMAN_DECISION_REQUIRED

    def __repr__(self):
        return (
            f"DecisionResult(decision={self.decision}, "
            f"by={self.detected_by}, confidence={self.confidence})"
        )


# ── Layer 1: Regex patterns for HUMAN_DECISION_REQUIRED emails ─────────────────
#
# Each entry: (compiled_pattern, reason_string)
# The reason string is shown in the Telegram notification.
#
# We check both subject and body. A match on either triggers HUMAN_DECISION_REQUIRED.
_DECISION_REGEX_RULES: list[tuple[re.Pattern, str]] = []

_RAW_REGEX_RULES: list[tuple[str, str]] = [

    # Direct personal questions — "Did you / Have you / Are you..."
    (
        r"\b(did you|have you|are you|were you|will you|would you|could you|can you|shall you)\b"
        r".{0,60}"
        r"\b(complet|finish|submit|attend|join|accept|confirm|agree|approv|done|ready|free|available|present|meet|send|deliver|review|check|sign|call)\w*\b",
        "This email is asking whether you personally completed, confirmed, or committed to something."
    ),

    # Availability / scheduling questions
    (
        r"\b(are you|will you be|would you be|can you be|could you be)\b"
        r".{0,40}"
        r"\b(available|free|around|there|present|online|at|in|attending)\b",
        "This email is asking about your personal availability or schedule."
    ),
    (
        r"\b(can you|could you|would you|will you)\b"
        r".{0,30}"
        r"\b(attend|join|come|make it|be there|be available|schedule|meet)\b",
        "This email is asking whether you can attend or join something."
    ),

    # Commitment / deadline questions
    (
        r"\b(will you|can you|would you|could you)\b"
        r".{0,40}"
        r"\b(submit|deliver|send|complete|finish|provide|share|upload|forward)\b",
        "This email is requesting a personal commitment or deadline confirmation from you."
    ),
    (
        r"\b(by when|when will you|when can you|what is your deadline|when do you plan)\b",
        "This email is asking for your personal timeline or deadline commitment."
    ),

    # Opinion / decision / agreement requests
    (
        r"\b(what (do|is) your (opinion|view|thought|take|stance|position|feedback|suggestion))\b",
        "This email is requesting your personal opinion or viewpoint."
    ),
    (
        r"\b(do you agree|do you think|do you feel|do you believe|do you support|do you approve)\b",
        "This email is asking for your personal agreement, approval, or opinion."
    ),
    (
        r"\b(please (confirm|let me know|advise|respond|reply|inform|decide|choose|select))\b"
        r".{0,60}"
        r"\b(you|your|availability|decision|preference|choice|opinion|answer)\b",
        "This email is explicitly requesting your personal confirmation or decision."
    ),

    # Invitation acceptance
    (
        r"\b(can you|would you|will you|could you)\b"
        r".{0,30}"
        r"\b(join|accept|take (up|on)|be part of|become|participate|collaborate|work with)\b",
        "This email is asking you to accept an invitation or join something."
    ),

    # Direct yes/no decision questions about the user
    (
        r"\b(did you|have you (already|yet)?)\b"
        r".{0,80}[?]",
        "This email contains a direct question about your past actions or status."
    ),

    # Scheduling a call / meeting
    (
        r"\b(schedule|set up|arrange|book|fix)\b"
        r".{0,30}"
        r"\b(a call|a meeting|a chat|a session|a discussion|a sync|a demo|a catch.?up)\b",
        "This email is requesting you to schedule a personal call or meeting."
    ),
    (
        r"\b(can we|could we|shall we|should we)\b"
        r".{0,30}"
        r"\b(meet|connect|talk|speak|discuss|catch up|hop on|jump on)\b",
        "This email is requesting a personal meeting or call with you."
    ),

    # Time-specific availability
    (
        r"\b(at|on|by)\b"
        r"\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|today|tonight|morning|afternoon|evening|night|weekend)\b"
        r".{0,50}"
        r"\b(available|free|work|meet|call|join|attend|come|be there)\b",
        "This email references a specific time and asks about your personal availability."
    ),

    # "Your decision" / "Your approval" / "Your confirmation"
    (
        r"\b(your (decision|approval|confirmation|consent|sign.?off|go.?ahead|greenlight|permission|authorization))\b",
        "This email is waiting for your personal decision or approval."
    ),

    # Explicit "let me know" with personal context
    (
        r"\blet me know\b"
        r".{0,60}"
        r"\b(if you|whether you|when you|your|you are|you will|you can|you have)\b",
        "This email is asking you to personally respond with your status or availability."
    ),
]

# Compile all patterns once at module load
_DECISION_REGEX_RULES = [
    (re.compile(pattern, re.IGNORECASE | re.DOTALL), reason)
    for pattern, reason in _RAW_REGEX_RULES
]


def detect_decision(
    parsed_email: dict,
    subject: str = "",
    body: str = "",
) -> DecisionResult:
    """
    Determine whether this email can be auto-replied or requires human decision.

    This is the main entry point. Call this AFTER generating a reply draft but
    BEFORE sending it. Only called for IMPORTANT emails (main.py handles gating).

    Args:
        parsed_email: Full parsed email dict from parser.py
        subject:      Email subject (can be passed separately for convenience)
        body:         Email body (can be passed separately for convenience)

    Returns:
        DecisionResult — check .requires_human() before sending any reply.
    """
    subject = subject or parsed_email.get("subject", "")
    body    = body    or parsed_email.get("body", "")

    logger.debug("Decision detection: %s", subject[:60])

    combined_text = f"{subject}\n{body}"

    # ── Layer 1: Regex fast scan ──────────────────────────────────────────────
    regex_result = _regex_scan(combined_text)

    if regex_result:
        decision, reason = regex_result
        logger.info(
            "🧠 HUMAN DECISION REQUIRED (regex): %s",
            subject[:50]
        )
        return DecisionResult(
            decision    = decision,
            reason      = reason,
            detected_by = "regex",
            confidence  = "HIGH",
        )

    # ── Layer 2: LLM deep scan (only if regex found nothing) ─────────────────
    llm_result = _llm_scan(subject, body[:_MAX_BODY_CHARS])

    if llm_result:
        decision, reason = llm_result
        logger.info(
            "🧠 HUMAN DECISION REQUIRED (llm): %s",
            subject[:50]
        )
        return DecisionResult(
            decision    = decision,
            reason      = reason,
            detected_by = "llm",
            confidence  = "MEDIUM",
        )

    # ── All clear — auto-reply is safe ───────────────────────────────────────
    logger.debug("✓ AUTO_REPLY_ALLOWED: %s", subject[:50])
    return DecisionResult(
        decision    = AUTO_REPLY_ALLOWED,
        reason      = "",
        detected_by = "none",
        confidence  = "HIGH",
    )


def _regex_scan(text: str) -> tuple[str, str] | None:
    """
    Run all compiled regex patterns against the text.
    Returns (decision, reason) on first match, None if clean (auto-reply safe).
    """
    for pattern, reason in _DECISION_REGEX_RULES:
        if pattern.search(text):
            return HUMAN_DECISION_REQUIRED, reason
    return None


def _llm_scan(subject: str, body: str) -> tuple[str, str] | None:
    """
    Ask the LLM to detect subtle decision-requiring emails that regex missed.

    Returns (HUMAN_DECISION_REQUIRED, reason) or None if auto-reply is safe.
    """

    prompt = f"""You are analyzing an email to decide if an AI assistant can reply automatically, or if the human must personally decide.

RULE: The AI must NEVER:
- Claim the user completed or did something
- Accept invitations on the user's behalf
- Confirm attendance or availability
- Make commitments (deadlines, deliverables)
- Express personal opinions or preferences
- Agree/disagree with proposals

These require the HUMAN to personally respond.

The AI CAN auto-reply if the email is:
- Informational (no question requiring personal knowledge)
- A notification or update (access approved, meeting link, submission confirmation)
- A thank-you or acknowledgment that just needs a polite acknowledgment
- A newsletter or broadcast

EMAIL:
SUBJECT: {subject}
BODY:
{body}

Respond in this EXACT format (two lines only):
DECISION: AUTO_REPLY_ALLOWED or HUMAN_DECISION_REQUIRED
REASON: one concise sentence explaining why

Nothing else."""

    try:
        response = _client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.0,
        )

        raw = response.choices[0].message.content.strip()
        logger.debug("LLM decision raw: %s", raw[:100])

        # Parse the response
        decision = None
        reason   = "This email may require your personal input or decision."

        for line in raw.splitlines():
            line = line.strip()
            if line.upper().startswith("DECISION:"):
                val = line.split(":", 1)[1].strip().upper()
                if HUMAN_DECISION_REQUIRED in val:
                    decision = HUMAN_DECISION_REQUIRED
                elif AUTO_REPLY_ALLOWED in val:
                    decision = AUTO_REPLY_ALLOWED
            elif line.upper().startswith("REASON:"):
                reason = line.split(":", 1)[1].strip()

        if decision == HUMAN_DECISION_REQUIRED:
            return HUMAN_DECISION_REQUIRED, reason

        return None  # AUTO_REPLY_ALLOWED or unparseable → safe to reply

    except Exception as e:
        logger.warning("LLM decision scan failed (non-critical): %s — defaulting to AUTO_REPLY_ALLOWED", e)
        return None  # On LLM failure, don't block the pipeline


# ── Convenience helper ─────────────────────────────────────────────────────────

def requires_human_decision(parsed_email: dict) -> bool:
    """Quick boolean check — use when you only need True/False."""
    result = detect_decision(parsed_email)
    return result.requires_human()
