# monitor.py
#
# UPDATED: Added Telegram callback polling for the Human Decision Layer.
#
# WHY THIS FILE EXISTS:
# Runs the email processing pipeline continuously, every N seconds.
# This is what you run in production — it never stops until you Ctrl+C it.
#
# NEW: Each cycle now also polls Telegram getUpdates to process button
# presses (✅ Send Draft / ✏️ Edit Reply / ❌ Ignore) from the inline
# keyboard sent when HUMAN_DECISION_REQUIRED emails are detected.
# This avoids needing a webhook server — the same polling loop handles both
# email fetching and Telegram callback processing.
#
# RUN WITH:
#   python monitor.py
# STOP WITH:
#   Ctrl+C

import time
import signal
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from utils.logger import get_logger
from notifications.telegram_service import send_message
from notifications.telegram_approval import (
    handle_callback_query,
    handle_incoming_text,
)
import main  # Import the orchestrator — we call main.run() each cycle

logger = get_logger(__name__)

INTERVAL = int(os.getenv("MONITOR_INTERVAL_SECONDS", 60))

_BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
_API_BASE    = f"https://api.telegram.org/bot{_BOT_TOKEN}"
_stats       = {"runs": 0, "errors": 0, "start_time": None}
_last_update_id = 0  # Track processed Telegram updates to avoid duplicates


def _on_shutdown(sig, frame):
    """Called when Ctrl+C or SIGTERM is received. Log cleanly and exit."""
    uptime = datetime.now() - _stats["start_time"]
    logger.info("Shutdown signal received")
    logger.info(
        "Monitor ran for %s | Cycles: %d | Errors: %d",
        uptime, _stats["runs"], _stats["errors"]
    )
    send_message(
        f"🛑 <b>AI Email Monitor stopped</b>\n"
        f"Uptime: {uptime}\n"
        f"Cycles completed: {_stats['runs']}"
    )
    sys.exit(0)


def poll_telegram_callbacks() -> None:
    """
    Poll Telegram getUpdates for incoming callback_query (button presses)
    and text messages (edit flow replies).

    Uses long-polling offset to avoid reprocessing old updates.
    Called once per monitor cycle, before main.run().
    """
    global _last_update_id

    if not _BOT_TOKEN:
        return

    try:
        import requests
        resp = requests.get(
            f"{_API_BASE}/getUpdates",
            params={
                "offset":          _last_update_id + 1,
                "timeout":         5,
                "allowed_updates": ["callback_query", "message"],
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            return

        updates = data.get("result", [])

        for update in updates:
            update_id = update.get("update_id", 0)
            _last_update_id = max(_last_update_id, update_id)

            # Route to the correct handler
            if "callback_query" in update:
                logger.info("📲 Telegram callback: %s",
                            update["callback_query"].get("data", "?"))
                try:
                    handle_callback_query(update)
                except Exception as e:
                    logger.error("Callback handler error: %s", e)

            elif "message" in update:
                msg_text = update["message"].get("text", "")
                if msg_text and not msg_text.startswith("/"):
                    logger.info("📝 Telegram text message (edit flow): %s chars", len(msg_text))
                    try:
                        handle_incoming_text(update)
                    except Exception as e:
                        logger.error("Text message handler error: %s", e)

    except Exception as e:
        logger.warning("Telegram poll failed (non-critical): %s", e)


def run_monitor():
    """Main monitoring loop. Runs until interrupted."""

    # Register signal handlers for clean shutdown
    signal.signal(signal.SIGINT, _on_shutdown)   # Ctrl+C
    signal.signal(signal.SIGTERM, _on_shutdown)  # kill / system shutdown

    _stats["start_time"] = datetime.now()

    logger.info("🚀 AI EMAIL MONITOR STARTED")
    logger.info("   Checking every %d seconds", INTERVAL)
    logger.info("   Telegram callback polling: %s", "enabled" if _BOT_TOKEN else "disabled")
    logger.info("   Press Ctrl+C to stop\n")

    send_message(
        f"🚀 <b>AI Email Monitor started</b>\n"
        f"Checking every {INTERVAL} seconds\n"
        f"🧠 Human Decision Layer: <b>active</b>"
    )

    while True:
        try:
            logger.info("▶ Cycle #%d starting...", _stats["runs"] + 1)

            # ── Step A: Process any pending Telegram button presses ───────────
            poll_telegram_callbacks()

            # ── Step B: Run the email processing pipeline ─────────────────────
            main.run()

            _stats["runs"] += 1
            logger.info("▶ Cycle #%d complete. Next in %ds\n", _stats["runs"], INTERVAL)

        except KeyboardInterrupt:
            raise  # Let the signal handler deal with it

        except Exception as e:
            _stats["errors"] += 1
            logger.error("❌ Cycle failed (error #%d): %s", _stats["errors"], e)

            # Send Telegram alert every 3rd consecutive error
            if _stats["errors"] % 3 == 0:
                send_message(
                    f"⚠️ <b>Monitor: {_stats['errors']} errors so far</b>\n"
                    f"Last: {str(e)[:300]}"
                )

        time.sleep(INTERVAL)


if __name__ == "__main__":
    run_monitor()
