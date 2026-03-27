from __future__ import annotations

import logging
import math
import os
from datetime import date, datetime, timezone
from dataclasses import dataclass
from typing import Literal, Optional

from ib_insync import IB, Contract, MarketOrder, Stock

from trading_bot import config

logger = logging.getLogger(__name__)

Signal = Literal["BUY", "SELL", "HOLD"]


def _to_utc_date(value: object) -> date | None:
    """Convert a datetime-like value to a UTC date for day-bound guardrails."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).date()


@dataclass
class DryRunSkipped:
    """Returned by execute_signal_as_market_order when DRYRUN mode prevents execution."""

    signal: Signal
    ib_symbol: str
    quantity: int


@dataclass
class OrderSkipped:
    """Returned when a BUY/SELL signal is skipped by pre-trade checks."""

    signal: Signal
    ib_symbol: str
    reason: Literal[
        "already_long",
        "already_flat",
        "kill_switch_enabled",
        "max_orders_per_day_reached",
        "max_position_size_exceeded",
        "max_daily_notional_exceeded",
        "missing_price_for_notional_cap",
        "orders_today_unavailable",
        "daily_notional_unavailable",
    ]


@dataclass
class IBKRConfig:
    """Connection parameters for TWS / IB Gateway."""

    host: str = config.IBKR_HOST
    port: int = config.IBKR_PORT
    client_id: int = config.IBKR_CLIENT_ID
    account: Optional[str] = config.IBKR_ACCOUNT
    exchange: str = "SMART"
    currency: str = config.IBKR_CURRENCY
    timeout: int = config.IBKR_TIMEOUT
    kill_switch: bool = config.IBKR_KILL_SWITCH
    max_orders_per_day: int = config.IBKR_MAX_ORDERS_PER_DAY
    max_position_size: int = config.IBKR_MAX_POSITION_SIZE
    max_daily_notional: float | None = (
        float(config.IBKR_MAX_DAILY_NOTIONAL)
        if config.IBKR_MAX_DAILY_NOTIONAL is not None
        else None
    )


class IBKRClient:
    """
    Thin wrapper around ib_insync for placing simple market orders.

    Intended to be used with TWS or IB Gateway running locally, ideally in
    paper trading mode first.
    """

    def __init__(self, cfg: IBKRConfig) -> None:
        """Initialise the client with connection parameters; does not connect yet."""
        self.cfg = cfg
        self.ib = IB()

    def __enter__(self) -> "IBKRClient":
        """Connect on entry; use as ``with IBKRClient(cfg) as client:``."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Disconnect on exit regardless of whether an exception was raised."""
        self.disconnect()

    def connect(self) -> None:
        """Connect to TWS / IB Gateway, raising ConnectionError on timeout."""
        if not self.ib.isConnected():
            logger.info(
                "Connecting to IBKR at %s:%d (client_id=%d)",
                self.cfg.host,
                self.cfg.port,
                self.cfg.client_id,
            )
            try:
                self.ib.connect(
                    self.cfg.host,
                    self.cfg.port,
                    clientId=self.cfg.client_id,
                    timeout=self.cfg.timeout,
                )
            except TimeoutError as exc:
                raise ConnectionError(
                    f"Timed out connecting to IBKR at {self.cfg.host}:{self.cfg.port}"
                    f" (client_id={self.cfg.client_id})"
                ) from exc

    def disconnect(self) -> None:
        """Disconnect from TWS / IB Gateway."""
        if self.ib.isConnected():
            logger.info("Disconnecting from IBKR")
            self.ib.disconnect()

    def get_current_position(self, symbol: str) -> int:
        """Return the current net share count for *symbol* (0 if no position or on error).

        Any exception raised by ``ib.positions()`` (e.g. connection loss) is
        caught, logged, and treated as 0 so callers receive a safe fallback
        rather than a raw network exception.
        """
        try:
            for pos in self.ib.positions():
                if pos.contract.symbol == symbol:
                    return int(pos.position)
        except Exception:
            logger.error("Failed to fetch positions for %s; assuming 0", symbol, exc_info=True)
        return 0

    def _build_stock_contract(self, symbol: str) -> Contract:
        """Build an ib_insync Stock contract for the given symbol."""
        return Stock(symbol, self.cfg.exchange, self.cfg.currency)

    def place_market_order(
        self,
        symbol: str,
        quantity: int,
        action: Literal["BUY", "SELL"],
    ):
        """Place a market order and return the ib_insync Trade object."""
        if quantity <= 0:
            raise ValueError("Quantity must be positive for a market order.")

        contract = self._build_stock_contract(symbol)
        order = MarketOrder(action, quantity)
        logger.info("Placing %s market order: %d x %s", action, quantity, symbol)
        trade = self.ib.placeOrder(contract, order)
        # Give IBKR a small moment to process the order so status is populated.
        self.ib.sleep(0.5)
        logger.info(
            "Order placed: id=%s status=%s",
            trade.order.orderId,
            trade.orderStatus.status,
        )
        return trade

    def get_today_order_count(self) -> int | None:
        """Return number of orders submitted today, or None if IBKR query fails."""
        try:
            today_utc = datetime.now(timezone.utc).date()
            count = 0
            for trade in self.ib.trades():
                status = getattr(getattr(trade, "orderStatus", None), "status", None)
                if status in {"Inactive", "Cancelled"}:
                    continue
                log_entries = list(getattr(trade, "log", []) or [])
                if not log_entries:
                    continue
                last_time = getattr(log_entries[-1], "time", None)
                if last_time is None:
                    continue
                if _to_utc_date(last_time) == today_utc:
                    count += 1
            return count
        except Exception:
            logger.error("Failed to fetch today's order count from IBKR", exc_info=True)
            return None

    def get_today_filled_notional(self) -> float | None:
        """Return today's filled notional in account currency, or None if unavailable."""
        try:
            today_utc = datetime.now(timezone.utc).date()
            total = 0.0
            for fill in self.ib.fills():
                exec_time = getattr(fill.execution, "time", None)
                if _to_utc_date(exec_time) != today_utc:
                    continue
                shares = abs(float(getattr(fill.execution, "shares", 0.0)))
                price = float(getattr(fill.execution, "price", 0.0))
                total += shares * price
            return total
        except Exception:
            logger.error("Failed to fetch today's filled notional from IBKR", exc_info=True)
            return None


def execute_signal_as_market_order(
    signal: Signal,
    *,
    ib_symbol: str,
    quantity: int,
    reference_price: float | None = None,
    cfg: Optional[IBKRConfig] = None,
):
    """
    Convenience helper: map a BUY/SELL/HOLD signal into a single market order.

    - BUY  -> BUY `quantity` shares (skipped if already long)
    - SELL -> SELL `quantity` shares (skipped if already flat)
    - HOLD -> no order

    Returns:
      - ``None`` for HOLD
      - :class:`DryRunSkipped` when ``DRYRUN`` is true
      - :class:`OrderSkipped` when the current account position makes the order redundant
      - an ib_insync Trade object on successful placement
    """
    if cfg is None:
        cfg = IBKRConfig()

    if signal == "HOLD":
        return None

    action: Literal["BUY", "SELL"]
    if signal == "BUY":
        action = "BUY"
    elif signal == "SELL":
        action = "SELL"
    else:
        raise ValueError(f"Unsupported signal {signal!r}")

    if os.environ.get("DRYRUN", "true").lower() != "false":
        logger.info("DRYRUN mode: skipping %s order for %d x %s", action, quantity, ib_symbol)
        return DryRunSkipped(signal=signal, ib_symbol=ib_symbol, quantity=quantity)

    if cfg.kill_switch:
        logger.error(
            "Kill switch enabled: blocking %s order for %d x %s",
            action,
            quantity,
            ib_symbol,
        )
        return OrderSkipped(signal=signal, ib_symbol=ib_symbol, reason="kill_switch_enabled")

    with IBKRClient(cfg) as client:
        orders_today = client.get_today_order_count()
        if orders_today is None:
            logger.error(
                "Skipping %s for %s: unable to evaluate orders/day guardrail",
                action,
                ib_symbol,
            )
            return OrderSkipped(signal=signal, ib_symbol=ib_symbol, reason="orders_today_unavailable")
        if orders_today >= cfg.max_orders_per_day:
            logger.warning(
                "Skipping %s for %s: max orders/day reached (%d/%d)",
                action,
                ib_symbol,
                orders_today,
                cfg.max_orders_per_day,
            )
            return OrderSkipped(signal=signal, ib_symbol=ib_symbol, reason="max_orders_per_day_reached")

        current_pos = client.get_current_position(ib_symbol)
        if action == "BUY" and current_pos + quantity > cfg.max_position_size:
            logger.warning(
                "Skipping BUY for %s: max position exceeded (current=%d + new=%d > limit=%d)",
                ib_symbol,
                current_pos,
                quantity,
                cfg.max_position_size,
            )
            return OrderSkipped(signal=signal, ib_symbol=ib_symbol, reason="max_position_size_exceeded")
        if action == "BUY" and current_pos > 0:
            logger.warning(
                "Skipping BUY: already holding %d shares of %s", current_pos, ib_symbol
            )
            return OrderSkipped(signal=signal, ib_symbol=ib_symbol, reason="already_long")
        if action == "SELL" and current_pos == 0:
            logger.warning("Skipping SELL: no position in %s", ib_symbol)
            return OrderSkipped(signal=signal, ib_symbol=ib_symbol, reason="already_flat")
        if cfg.max_daily_notional is not None:
            if reference_price is None or math.isnan(reference_price):
                logger.error(
                    "Skipping %s for %s: max daily notional is configured but no reference price was provided",
                    action,
                    ib_symbol,
                )
                return OrderSkipped(signal=signal, ib_symbol=ib_symbol, reason="missing_price_for_notional_cap")
            today_notional = client.get_today_filled_notional()
            if today_notional is None:
                logger.error(
                    "Skipping %s for %s: unable to evaluate daily notional guardrail",
                    action,
                    ib_symbol,
                )
                return OrderSkipped(signal=signal, ib_symbol=ib_symbol, reason="daily_notional_unavailable")
            projected_notional = today_notional + float(quantity) * reference_price
            if projected_notional > cfg.max_daily_notional:
                logger.warning(
                    "Skipping %s for %s: max daily notional exceeded (projected=%.2f > limit=%.2f)",
                    action,
                    ib_symbol,
                    projected_notional,
                    cfg.max_daily_notional,
                )
                return OrderSkipped(signal=signal, ib_symbol=ib_symbol, reason="max_daily_notional_exceeded")
        trade = client.place_market_order(
            symbol=ib_symbol,
            quantity=quantity,
            action=action,
        )
    return trade
