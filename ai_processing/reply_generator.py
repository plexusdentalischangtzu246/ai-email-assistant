# ai_processing/reply_generator.py
#
# WHY THIS FILE EXISTS:
# Generates a contextually appropriate email reply draft.
# The generated text is passed to gmail_sender.py to actually send,
# or to gmail_draft_creator.py to save as a draft for review.
#
# FIX FROM YOUR ORIGINAL CODE:
# Your version was hardcoded to "Muni" with a specific Instagram handle.
# That works for one person's personal project but breaks for anyone else.
# Fixed: the identity comes from environment variables so anyone can
# configure it for themselves without touching the code.
#
# Also fixed: your version had no tone control.
# Added tone parameter so main.py can request "professional" vs "brief"
# depending on the email category.
#
# WHY temperature=0.7:
# Replies benefit from some creativity to sound natural.
# Higher temperature than classification or summary.

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

# Read the assistant's identity from environment
# Set YOUR_NAME and YOUR_ASSISTANT_NAME in your .env file
_OWNER_NAME      = os.getenv("YOUR_NAME", "the recipient")
_ASSISTANT_NAME  = os.getenv("YOUR_ASSISTANT_NAME", "AI Assistant")


def generate_reply(
    sender: str,
    subject: str,
    body: str,
    tone: str = "professional",
) -> str:
    """
    Generate a context-aware email reply draft.

    Args:
        sender:  Who sent the original email (for context)
        subject: Email subject
        body:    Email body
        tone:    "professional" | "casual" | "brief"

    Returns:
        Reply body text, ready to send.
        Does NOT include Subject or To headers — those are added by gmail_sender.py.
    """

    tone_map = {
        "professional": "professional and clear (3-5 sentences)",
        "casual":       "friendly and conversational (2-4 sentences)",
        "brief":        "very brief, just acknowledge and confirm next step (1-2 sentences)",
    }
    tone_desc = tone_map.get(tone, tone_map["professional"])

    prompt = f"""You are {_ASSISTANT_NAME}, the AI email assistant for {_OWNER_NAME}.

Generate an email reply that is {tone_desc}.

Rules:
- Do NOT include subject line or To/From headers
- Do NOT use placeholder text like [Your Name]
- Start naturally, not with "I hope this email finds you well"
- Directly address what the email is about
- Sound human, not corporate

ORIGINAL EMAIL:
FROM: {sender}
SUBJECT: {subject}
BODY:
{body[:_MAX_BODY_CHARS]}

Write ONLY the reply body:"""

    logger.debug("Generating reply for: %s", subject[:50])

    try:
        response = _client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.7,
        )
        result = response.choices[0].message.content.strip()
        logger.debug("Reply generated (%d chars)", len(result))
        return result

    except Exception as e:
        logger.error("Reply generation failed: %s", e)
        return f"Thank you for your email. I'll get back to you shortly.\n\n— {_OWNER_NAME}'s AI Assistant"
