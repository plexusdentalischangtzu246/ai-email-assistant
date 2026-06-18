# ai_processing/summarizer.py
#
# WHY THIS FILE EXISTS:
# Takes a parsed email and uses an LLM to produce a 3-bullet summary.
# The summary is stored in the database and shown on the dashboard,
# so you can understand any email without reading the full body.
#
# FIX FROM YOUR ORIGINAL CODE:
# Your version passed the entire parsed_email dict as the prompt text,
# which would print something like "{'id': 'abc', 'subject': ...}".
# The LLM was summarizing a Python dict, not the actual email.
# Fixed: we explicitly extract subject + body and build a clean prompt.
#
# WHY temperature=0.3:
# Lower temperature = more focused, consistent, factual output.
# For summarization we want accuracy, not creativity.

import os
from openai import OpenAI
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

# Module-level client — created once when the module is first imported.
# This avoids creating a new HTTP client on every function call.
_client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

_MODEL = "openai/gpt-4o-mini"
_MAX_BODY_CHARS = 3000  # Truncate body to control token usage and cost


def summarize_email(parsed_email: dict) -> str:
    """
    Generate a 3-bullet summary of an email using AI.

    Args:
        parsed_email: Dict from parser.py with keys: subject, sender, body

    Returns:
        3-bullet point string summarizing the email's key points.
        Returns an error string if the API call fails.
    """

    subject = parsed_email.get("subject", "")
    sender  = parsed_email.get("sender", "")
    body    = parsed_email.get("body", "")[:_MAX_BODY_CHARS]

    prompt = f"""Summarize this email in exactly 3 concise bullet points.
Focus on: key information, any required actions, and deadlines.
Be specific — avoid vague statements like "the email is about...".

FROM: {sender}
SUBJECT: {subject}
BODY:
{body}

Return ONLY the 3 bullet points. Start each with •"""

    logger.debug("Summarizing: %s", subject[:50])

    try:
        response = _client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3,
        )
        result = response.choices[0].message.content.strip()
        logger.debug("Summary done (%d chars)", len(result))
        return result

    except Exception as e:
        logger.error("Summarization failed: %s", e)
        return f"Summary unavailable: {e}"
