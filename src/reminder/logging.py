"""Logging utilities for the reminder app."""

import logging
from pathlib import Path

LOG_DIR = Path.home() / ".local" / "share" / "reminder"
LOG_FILE = LOG_DIR / "reminder.log"


def setup_logging() -> logging.Logger:
    """Setup file logging and return logger."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("reminder")
    logger.setLevel(logging.DEBUG)

    # File handler
    handler = logging.FileHandler(LOG_FILE)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


logger = setup_logging()
