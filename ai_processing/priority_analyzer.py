# ai_processing/priority_analyzer.py
#
# WHY THIS FILE EXISTS:
# Not all IMPORTANT emails are equal. This file goes deeper:
# it assigns a 1-10 score, an urgency level, and says whether
# you need to take action. This helps the dashboard show you
# the most urgent things first.
#
# FIX FROM YOUR ORIGINAL CODE:
# Your version used "openai/gpt-oss-20b:free" which is not a real
# OpenRouter model name and will cause API errors.
# Fixed: using "openai/gpt-4o-mini" which is stable and affordable.
#
# Also removed the duplicate priority.py file — you had both
# priority.py and priority_analyzer.py doing the same thing.
# monitor.py was importing from priority.py which no longer exists here.
# Now there is ONE file, and both main.py and monitor.py import from it.

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


def analyze_priority(subject: str, body: str) -> str:
    """
    Analyze email urgency and return a structured priority string.

    Args:
        subject: Email subject line
        body:    Email body text

    Returns:
        Formatted string like:
            "PRIORITY: 8/10
             URGENCY: HIGH
             ACTION: YES"

    This raw string is stored in the database as-is.
    The dashboard displays it directly.
    """

    prompt = f"""Analyze this email and rate its priority.

Scoring guide:
  9-10  CRITICAL  — Legal, financial, medical, urgent deadline within 24h
  7-8   HIGH      — Important work task, client request, time-sensitive
  5-6   MEDIUM    — Standard task, follow-up, non-urgent request
  3-4   LOW       — Newsletter, FYI, non-actionable
  1-2   MINIMAL   — Promotion, spam, automated notification

SUBJECT: {subject}
BODY: {body[:_MAX_BODY_CHARS]}

Respond in EXACTLY this format with no other text:
PRIORITY: X/10
URGENCY: LOW/MEDIUM/HIGH
ACTION: YES/NO"""

    logger.debug("Analyzing priority for: %s", subject[:50])

    try:
        response = _client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.2,
        )
        result = response.choices[0].message.content.strip()
        logger.debug("Priority: %s", result.replace("\n", " | "))
        return result

    except Exception as e:
        logger.error("Priority analysis failed: %s", e)
        return "PRIORITY: 5/10\nURGENCY: MEDIUM\nACTION: NO"
