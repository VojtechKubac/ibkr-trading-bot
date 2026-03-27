"""Central configuration loaded from environment / .env file.

All modules should import constants from here rather than reading
``os.environ`` directly.  Calling :func:`load_dotenv` at import time is
intentional: the function is a no-op if no ``.env`` file is present.
"""
from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation

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


def _parse_float_env(name: str, default: float) -> float:
    """Read a float from the environment, raising a clear error on bad values."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(
            f"Environment variable {name}={raw!r} is not a valid float"
        ) from None


def _parse_bool_env(name: str, default: bool) -> bool:
    """Read a bool from the environment using true/false style values."""
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"Environment variable {name}={raw!r} is not a valid boolean"
    )


def _parse_decimal_env(name: str, default: str) -> Decimal:
    """Read a Decimal from the environment without float intermediates."""
    raw = os.getenv(name)
    value = default if raw is None else raw.strip()
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError(
            f"Environment variable {name}={value!r} is not a valid decimal"
        ) from None


def _parse_optional_decimal_env(name: str) -> Decimal | None:
    """Read an optional Decimal from the environment (blank/absent -> None)."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    try:
        return Decimal(raw.strip())
    except InvalidOperation:
        raise ValueError(
            f"Environment variable {name}={raw!r} is not a valid decimal"
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
# Weekly runner
# ---------------------------------------------------------------------------
DRYRUN: bool = _parse_bool_env("DRYRUN", True)
IBKR_ENABLE: bool = _parse_bool_env("IBKR_ENABLE", False)
SIGNAL_STRATEGY: str = os.getenv("SIGNAL_STRATEGY", "simple").strip().lower()
STOP_LOSS_PCT: float = _parse_float_env("STOP_LOSS_PCT", 0.15)
POSITION_ALLOCATION_PCT: float = _parse_float_env("POSITION_ALLOCATION_PCT", 0.25)
PORTFOLIO_VALUE: Decimal = _parse_decimal_env("PORTFOLIO_VALUE", "10000")

# ---------------------------------------------------------------------------
# IBKR execution guardrails
# ---------------------------------------------------------------------------
IBKR_KILL_SWITCH: bool = _parse_bool_env("IBKR_KILL_SWITCH", False)
IBKR_MAX_ORDERS_PER_DAY: int = _parse_int_env("IBKR_MAX_ORDERS_PER_DAY", 5)
IBKR_MAX_POSITION_SIZE: int = _parse_int_env("IBKR_MAX_POSITION_SIZE", 1_000_000)
IBKR_MAX_DAILY_NOTIONAL: Decimal | None = _parse_optional_decimal_env(
    "IBKR_MAX_DAILY_NOTIONAL"
)

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
DB_PATH: str = os.getenv("DB_PATH", "trading_bot.db")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str | None = os.getenv("LOG_FILE") or None
