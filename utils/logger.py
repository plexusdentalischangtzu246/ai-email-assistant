# utils/logger.py
#
# WHY THIS FILE EXISTS:
# Every module needs logging. Instead of each file setting up its own
# logging config (which causes duplicate logs and inconsistent formats),
# we configure logging ONCE here and every other module just calls
# get_logger(__name__) to get a properly configured logger.
#
# WHY NOT print()?
# print() has no timestamp, no log level, no module name, and can't
# be written to a file. When something breaks at 3am on your server,
# you need logs that tell you WHEN it broke, WHERE it broke, and WHY.
# logging gives you all of that automatically.

import logging
import os
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

load_dotenv()

# Read log level from environment — INFO in production, DEBUG when developing
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Log format: timestamp | level | which module | the message
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Track if we've already configured logging to prevent duplicate handlers
_configured = False


def _setup():
    """Configure the root logger once. All other loggers inherit from it."""
    global _configured
    if _configured:
        return

    # Create logs/ directory if it doesn't exist
    Path("logs").mkdir(exist_ok=True)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    # Handler 1: Print to terminal so you can watch live
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    # Handler 2: Write to rotating file so you have history
    # RotatingFileHandler: when app.log hits 5MB, rename to app.log.1
    # and start a fresh app.log. Keeps last 3 files before deleting.
    file_handler = RotatingFileHandler(
        "logs/app.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    # Apply to root logger — all child loggers inherit these handlers
    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    root.addHandler(console)
    root.addHandler(file_handler)

    # Silence noisy third-party libraries
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)
    logging.getLogger("google.auth").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger for a module.

    Call this at the TOP of every module file like this:
        from utils.logger import get_logger
        logger = get_logger(__name__)

    Then use it anywhere in that file:
        logger.info("Processing email: %s", subject)
        logger.warning("No body found in email")
        logger.error("API call failed: %s", error)
        logger.debug("Full payload: %s", payload)  # only shown in DEBUG mode
    """
    _setup()
    return logging.getLogger(name)
