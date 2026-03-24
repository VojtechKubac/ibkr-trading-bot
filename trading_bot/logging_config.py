"""Logging setup for the trading bot.

Call :func:`setup_logging` once at the start of the process (e.g. in
``main.py``) before any other imports emit log records.  Subsequent calls are
idempotent.
"""
from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

_configured = False


def setup_logging() -> None:
    """Configure the root logger from environment variables.

    Reads ``LOG_LEVEL`` (default ``INFO``) and ``LOG_FILE`` (default stdout)
    from the environment.  Safe to call multiple times; only the first call
    has any effect.
    """
    global _configured
    if _configured:
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_file = os.getenv("LOG_FILE") or None

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    handler: logging.Handler
    if log_file:
        handler = logging.FileHandler(log_file)
    else:
        handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    _configured = True
