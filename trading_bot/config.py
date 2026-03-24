"""Central configuration loaded from environment / .env file.

All modules should import constants from here rather than reading
``os.environ`` directly.  Calling :func:`load_dotenv` at import time is
intentional: the function is a no-op if no ``.env`` file is present.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# IBKR connection defaults
# ---------------------------------------------------------------------------
IBKR_HOST: str = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT: int = int(os.getenv("IBKR_PORT", "7497"))
IBKR_CLIENT_ID: int = int(os.getenv("IBKR_CLIENT_ID", "1"))
IBKR_ACCOUNT: str | None = os.getenv("IBKR_ACCOUNT") or None
IBKR_CURRENCY: str = os.getenv("IBKR_CURRENCY", "EUR")

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
DB_PATH: str = os.getenv("DB_PATH", "trading_bot.db")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str | None = os.getenv("LOG_FILE") or None
