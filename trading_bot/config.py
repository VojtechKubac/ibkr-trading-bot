"""Central configuration loaded from environment / .env file.

All modules should import constants from here rather than reading
``os.environ`` directly.  Calling :func:`load_dotenv` at import time is
intentional: the function is a no-op if no ``.env`` file is present.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _parse_int_env(name: str, default: int) -> int:
    """Read an integer from the environment, raising a clear error on bad values."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(
            f"Environment variable {name}={raw!r} is not a valid integer"
        ) from None


# ---------------------------------------------------------------------------
# IBKR connection defaults
# ---------------------------------------------------------------------------
IBKR_HOST: str = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT: int = _parse_int_env("IBKR_PORT", 7497)
IBKR_CLIENT_ID: int = _parse_int_env("IBKR_CLIENT_ID", 1)
IBKR_TIMEOUT: int = _parse_int_env("IBKR_TIMEOUT", 4)
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
