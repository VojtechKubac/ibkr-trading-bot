"""Weekly entry point for the trading bot.

Runs the Phase 1 signal check for each asset in ``WEEKLY_SYMBOLS`` and
optionally executes orders via IBKR when ``DRYRUN=false``.

Usage::

    DRYRUN=true python run_weekly.py                        # dry run, no orders
    DRYRUN=false IBKR_ENABLE=true python run_weekly.py     # live/paper execution
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Optional

from trading_bot import config
from trading_bot.assets import get_asset
from trading_bot.broker_ibkr import (
    DryRunSkipped,
    IBKRConfig,
    OrderSkipped,
    execute_signal_as_market_order,
)
from trading_bot.data import fetch_ohlcv
from trading_bot.logging_config import setup_logging
from trading_bot.scoring import ScoringConfig, weighted_signal_for_row
from trading_bot.signals import IndicatorConfig, enrich_with_indicators, latest_signal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Runtime configuration from environment
# ---------------------------------------------------------------------------
WEEKLY_SYMBOLS: list[str] = [
    s.strip() for s in os.getenv("WEEKLY_SYMBOLS", "vwce").split(",") if s.strip()
]
STOP_LOSS_PCT: float = float(os.getenv("STOP_LOSS_PCT", "0.15"))
POSITION_ALLOCATION_PCT: float = float(os.getenv("POSITION_ALLOCATION_PCT", "0.25"))
# Total portfolio value used to size orders when IBKR account query is unavailable.
PORTFOLIO_VALUE: float = float(os.getenv("PORTFOLIO_VALUE", "10000"))
# Explicit second guard: must be true in addition to DRYRUN=false before orders are placed.
IBKR_ENABLE: bool = os.getenv("IBKR_ENABLE", "false").lower() == "true"
# Signal strategy: "simple" uses Phase 1 MA rules; "weighted" uses the composite scoring engine.
SIGNAL_STRATEGY: str = os.getenv("SIGNAL_STRATEGY", "simple").strip().lower()
_VALID_SIGNAL_STRATEGIES = {"simple", "weighted"}
if SIGNAL_STRATEGY not in _VALID_SIGNAL_STRATEGIES:
    raise ValueError(
        f"Invalid SIGNAL_STRATEGY={SIGNAL_STRATEGY!r}; expected one of {_VALID_SIGNAL_STRATEGIES}"
    )


# ---------------------------------------------------------------------------
# SQLite helpers — track entry price and quantity for the stop-loss check
# ---------------------------------------------------------------------------

def init_db(db_path: str) -> sqlite3.Connection:
    """Open (or create) the SQLite DB and ensure the positions table exists."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS positions (
            symbol      TEXT    PRIMARY KEY,
            entry_price REAL    NOT NULL,
            quantity    INTEGER NOT NULL,
            opened_at   TEXT    NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def get_position(conn: sqlite3.Connection, symbol: str) -> Optional[dict]:
    """Return ``{"entry_price": ..., "quantity": ...}`` for *symbol*, or ``None``."""
    row = conn.execute(
        "SELECT entry_price, quantity FROM positions WHERE symbol = ?", (symbol,)
    ).fetchone()
    return {"entry_price": row[0], "quantity": row[1]} if row else None


def save_position(
    conn: sqlite3.Connection, symbol: str, entry_price: float, quantity: int
) -> None:
    """Upsert a position record after a BUY is executed."""
    conn.execute(
        """
        INSERT OR REPLACE INTO positions (symbol, entry_price, quantity, opened_at)
        VALUES (?, ?, ?, ?)
        """,
        (symbol, entry_price, quantity, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def delete_position(conn: sqlite3.Connection, symbol: str) -> None:
    """Remove the position record after a SELL is executed."""
    conn.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
    conn.commit()


# ---------------------------------------------------------------------------
# Stop-loss helper
# ---------------------------------------------------------------------------

def is_stop_loss_triggered(
    current_price: float, entry_price: float, stop_loss_pct: float
) -> bool:
    """Return True if *current_price* has fallen more than *stop_loss_pct* below *entry_price*."""
    return (current_price - entry_price) / entry_price <= -stop_loss_pct


# ---------------------------------------------------------------------------
# Per-symbol processing
# ---------------------------------------------------------------------------

def run_symbol(symbol_key: str, conn: sqlite3.Connection) -> None:
    """Fetch data, compute signal, and optionally execute for one asset."""
    asset = get_asset(symbol_key)

    try:
        df = fetch_ohlcv(asset.yahoo_symbol)
    except Exception:
        logger.error("Failed to fetch data for %s; skipping", symbol_key, exc_info=True)
        return

    df = enrich_with_indicators(df, IndicatorConfig())
    current_price = float(df.iloc[-1]["close"])
    position = get_position(conn, asset.ib_symbol)

    if position and is_stop_loss_triggered(
        current_price, position["entry_price"], STOP_LOSS_PCT
    ):
        logger.warning(
            "%s: stop-loss triggered (entry=%.2f current=%.2f threshold=%.0f%%)",
            symbol_key,
            position["entry_price"],
            current_price,
            STOP_LOSS_PCT * 100,
        )
        signal = "SELL"
    elif SIGNAL_STRATEGY == "weighted":
        signal = weighted_signal_for_row(df.iloc[-1], ScoringConfig())
        logger.debug("%s: weighted strategy selected signal=%s", symbol_key, signal)
    else:
        _, signal, _ = latest_signal(df)

    logger.info("%s: signal=%s price=%.2f", symbol_key, signal, current_price)

    if os.getenv("DRYRUN", "true").lower() != "false":
        logger.info("%s: DRYRUN — would execute: %s", symbol_key, signal)
        return

    if not IBKR_ENABLE:
        logger.error(
            "%s: refusing execution — IBKR_ENABLE is not true (DRYRUN=false alone is insufficient)",
            symbol_key,
        )
        return

    # Compute quantity: for SELL use the tracked position size; for BUY use allocation sizing.
    if signal == "SELL":
        if not position:
            logger.info("%s: SELL skipped — no tracked position to sell", symbol_key)
            return
        quantity = int(position["quantity"])
    else:
        quantity = max(1, int(PORTFOLIO_VALUE * POSITION_ALLOCATION_PCT / current_price))

    try:
        result = execute_signal_as_market_order(
            signal,  # type: ignore[arg-type]
            ib_symbol=asset.ib_symbol,
            quantity=quantity,
            cfg=IBKRConfig(),
        )
    except Exception:
        logger.error("Execution failed for %s", symbol_key, exc_info=True)
        return

    if result is None:
        logger.info("%s: HOLD — no order sent", symbol_key)
    elif isinstance(result, OrderSkipped):
        logger.info("%s: order skipped (%s)", symbol_key, result.reason)
    elif isinstance(result, DryRunSkipped):
        logger.info("%s: DRYRUN sentinel — %s skipped", symbol_key, result.signal)
    else:
        logger.info(
            "%s: order placed — id=%s status=%s",
            symbol_key,
            result.order.orderId,
            result.orderStatus.status,
        )
        if signal == "BUY":
            fill_price = float(getattr(result.orderStatus, "avgFillPrice", 0) or current_price)
            save_position(conn, asset.ib_symbol, fill_price, quantity)
        elif signal == "SELL":
            delete_position(conn, asset.ib_symbol)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the weekly signal check and optional execution for all configured assets."""
    setup_logging()
    logger.info("Weekly run starting — symbols=%s dryrun=%s", WEEKLY_SYMBOLS, os.getenv("DRYRUN", "true"))

    conn = init_db(config.DB_PATH)
    try:
        for symbol_key in WEEKLY_SYMBOLS:
            try:
                run_symbol(symbol_key, conn)
            except Exception:
                logger.error("Unhandled error processing %s", symbol_key, exc_info=True)
    finally:
        conn.close()

    logger.info("Weekly run complete")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Fatal error in weekly run")
        sys.exit(1)
