# setup_check.py
#
# Run this BEFORE anything else to verify your setup is correct.
# It checks every dependency and configuration so you know
# exactly what's ready and what still needs to be done.
#
# RUN WITH:
#   python setup_check.py

import sys
import os
from pathlib import Path

print("=" * 55)
print("  AI Email Assistant — Setup Check")
print("=" * 55)

checks_passed = 0
checks_failed = 0


def check(label, fn):
    global checks_passed, checks_failed
    try:
        result = fn()
        status = result if isinstance(result, str) else "OK"
        print(f"  ✅ {label:<35} {status}")
        checks_passed += 1
    except Exception as e:
        print(f"  ❌ {label:<35} {e}")
        checks_failed += 1


# ── Python version ────────────────────────────────────────────────────────────
check("Python version",
      lambda: f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
      if sys.version_info >= (3, 9)
      else (_ for _ in ()).throw(Exception("Need Python 3.9+")))

# ── Required packages ─────────────────────────────────────────────────────────
check("google-api-python-client", lambda: __import__("googleapiclient.discovery") and "installed")
check("google-auth-oauthlib",     lambda: __import__("google_auth_oauthlib") and "installed")
check("openai SDK",               lambda: __import__("openai") and "installed")
check("python-dotenv",            lambda: __import__("dotenv") and "installed")
check("beautifulsoup4",           lambda: __import__("bs4") and "installed")
check("requests",                 lambda: __import__("requests") and "installed")
check("streamlit",                lambda: __import__("streamlit") and "installed")
check("pandas",                   lambda: __import__("pandas") and "installed")

# ── Project files ─────────────────────────────────────────────────────────────
check("credentials.json exists",
      lambda: "found" if Path("credentials.json").exists()
      else (_ for _ in ()).throw(Exception("MISSING — download from Google Cloud Console")))

check(".env file exists",
      lambda: "found" if Path(".env").exists()
      else (_ for _ in ()).throw(Exception("MISSING — copy .env.example to .env and fill it in")))

# ── Environment variables ─────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

check("OPENROUTER_API_KEY set",
      lambda: "set ✓" if os.getenv("OPENROUTER_API_KEY", "").startswith("sk-")
      else (_ for _ in ()).throw(Exception("not set or wrong format in .env")))

check("TELEGRAM_BOT_TOKEN set",
      lambda: "set ✓" if os.getenv("TELEGRAM_BOT_TOKEN", "")
      else (_ for _ in ()).throw(Exception("not set in .env")))

check("TELEGRAM_CHAT_ID set",
      lambda: "set ✓" if os.getenv("TELEGRAM_CHAT_ID", "")
      else (_ for _ in ()).throw(Exception("not set in .env")))

# ── Module imports ─────────────────────────────────────────────────────────────
check("utils.logger imports",            lambda: __import__("utils.logger") and "OK")
check("auth.gmail_auth imports",         lambda: __import__("auth.gmail_auth") and "OK")
check("email_engine.fetcher imports",    lambda: __import__("email_engine.fetcher") and "OK")
check("email_engine.parser imports",     lambda: __import__("email_engine.parser") and "OK")
check("ai_processing.summarizer",        lambda: __import__("ai_processing.summarizer") and "OK")
check("ai_processing.classifier",        lambda: __import__("ai_processing.classifier") and "OK")
check("ai_processing.priority_analyzer", lambda: __import__("ai_processing.priority_analyzer") and "OK")
check("ai_processing.reply_generator",   lambda: __import__("ai_processing.reply_generator") and "OK")
check("database.db_manager imports",     lambda: __import__("database.db_manager") and "OK")
check("storage.data_store imports",      lambda: __import__("storage.data_store") and "OK")
check("notifications.telegram_service",  lambda: __import__("notifications.telegram_service") and "OK")
check("drafts.gmail_sender imports",     lambda: __import__("drafts.gmail_sender") and "OK")

# ── Summary ───────────────────────────────────────────────────────────────────
print("=" * 55)
print(f"  Passed: {checks_passed}  |  Failed: {checks_failed}")
print("=" * 55)

if checks_failed == 0:
    print("\n  🎉 All checks passed! You're ready to run:\n")
    print("     python auth/gmail_auth.py       ← authenticate first")
    print("     python main.py                  ← process emails once")
    print("     python monitor.py               ← run continuously")
    print("     streamlit run dashboard/app.py  ← open dashboard\n")
else:
    print(f"\n  ⚠️  Fix the {checks_failed} failed check(s) above before running.\n")
    sys.exit(1)
