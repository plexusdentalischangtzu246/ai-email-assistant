# auth/gmail_auth.py
#
# WHY THIS FILE EXISTS:
# Gmail requires OAuth2 authentication before you can read or send emails.
# This file handles the ENTIRE auth lifecycle in one place:
#   - First run: opens your browser so you can log in to Google
#   - Saves the login token to token.json so you don't log in again
#   - Auto-refreshes the token when it expires (happens every ~1 hour)
#   - Returns a ready-to-use Gmail service object to every other module
#
# WHY ONE FILE FOR AUTH:
# Four modules need Gmail access (fetcher, sender, draft_creator).
# If auth logic was duplicated in each, a Google API change would
# require fixing it in four places. One file = one fix.
#
# credentials.json vs token.json — THE most confused concept:
#   credentials.json = your APP's identity (downloaded from Google Cloud once)
#   token.json       = the USER's permission grant (created at runtime)
#
# Think of it like:
#   credentials.json = your passport (proves who you are)
#   token.json       = your visa (proves you're allowed in)

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from utils.logger import get_logger

logger = get_logger(__name__)

# ── SCOPES ───────────────────────────────────────────────────────────────────
# Scopes = what permissions we're requesting from the user.
# Principle of least privilege: only request what you actually need.
#
# gmail.readonly  → read emails
# gmail.modify    → mark as read, add labels
# gmail.send      → send emails (needed for auto-reply)
# gmail.compose   → create drafts
#
# IMPORTANT: If you add or remove scopes after a user has already
# logged in, delete token.json and re-authenticate. Google detects
# scope mismatches and rejects the old token.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
]

# ── FILE PATHS ────────────────────────────────────────────────────────────────
# Path(__file__) = this file's location (auth/gmail_auth.py)
# .parent        = auth/
# .parent.parent = project root (ai-email-assistant/)
# This works on Windows, Mac, and Linux regardless of where the project lives.
# Never use hardcoded paths like /home/arshad/project/... — that breaks
# on every other machine.
BASE_DIR = Path(__file__).parent.parent.resolve()
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"


def get_gmail_service():
    """
    Authenticate with Gmail and return a ready-to-use service object.

    This is the ONLY function other modules should call.
    They don't need to know anything about OAuth — they just call
    get_gmail_service() and get back an object they can use.

    Returns:
        googleapiclient.discovery.Resource — Gmail API service object

    Raises:
        FileNotFoundError — if credentials.json is missing
    """

    # Fail immediately with a helpful message if credentials are missing.
    # Better than a cryptic error 10 lines later.
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"\ncredentials.json not found at: {CREDENTIALS_FILE}\n\n"
            "To fix this:\n"
            "  1. Go to https://console.cloud.google.com\n"
            "  2. Create a project → Enable Gmail API\n"
            "  3. Credentials → OAuth 2.0 Client IDs → Desktop App\n"
            "  4. Download JSON → rename to credentials.json\n"
            "  5. Place in your project root folder\n"
        )

    creds = None

    # ── Step 1: Try loading saved token ──────────────────────────────────────
    if TOKEN_FILE.exists():
        logger.debug("Found existing token at %s", TOKEN_FILE)
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    # ── Step 2: Refresh or re-authenticate if needed ─────────────────────────
    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            # Token expired but refresh token exists → silent refresh
            # No browser needed. This runs automatically every ~1 hour.
            logger.info("Token expired — refreshing silently...")
            creds.refresh(Request())
            logger.info("Token refreshed successfully")

        else:
            # No token at all → full browser login (first run only)
            logger.info("Starting Gmail login — your browser will open...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            # port=0 = let the OS pick any available port (avoids conflicts)
            creds = flow.run_local_server(port=0)
            logger.info("Gmail login successful")

        # ── Step 3: Save token for next run ──────────────────────────────────
        TOKEN_FILE.write_text(creds.to_json())
        logger.debug("Token saved to %s", TOKEN_FILE)

    # ── Step 4: Build and return service object ───────────────────────────────
    service = build("gmail", "v1", credentials=creds)
    logger.debug("Gmail service ready")
    return service


# ── Run this file directly to test authentication ─────────────────────────────
# python auth/gmail_auth.py
if __name__ == "__main__":
    print("Testing Gmail authentication...")
    try:
        service = get_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        print(f"\n✅ Connected successfully!")
        print(f"   Email:    {profile['emailAddress']}")
        print(f"   Messages: {profile['messagesTotal']:,}")
    except FileNotFoundError as e:
        print(e)
    except Exception as e:
        print(f"\n❌ Authentication failed: {e}")
