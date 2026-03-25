from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal, Optional

from ib_insync import IB, Contract, MarketOrder, Stock

from trading_bot import config

logger = logging.getLogger(__name__)

Signal = Literal["BUY", "SELL", "HOLD"]


@dataclass
class DryRunSkipped:
    """Returned by execute_signal_as_market_order when DRYRUN mode prevents execution."""

    signal: Signal
    ib_symbol: str
    quantity: int


@dataclass
class OrderSkipped:
    """Returned when a BUY/SELL is skipped because the account position makes it redundant."""

    signal: Signal
    ib_symbol: str
    reason: Literal["already_long", "already_flat"]


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
            logger.info("Connecting to IBKR at %s:%d (client_id=%d)", self.cfg.host, self.cfg.port, self.cfg.client_id)
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
        logger.info("Order placed: id=%s status=%s", trade.order.orderId, trade.orderStatus.status)
        return trade


def execute_signal_as_market_order(
    signal: Signal,
    *,
    ib_symbol: str,
    quantity: int,
    cfg: Optional[IBKRConfig] = None,
):
    """
    Convenience helper: map a BUY/SELL/HOLD signal into a single market order.

    - BUY  -> BUY `quantity` shares (skipped if already long)
    - SELL -> SELL `quantity` shares (skipped if already flat)
    - HOLD -> no order

    Returns:
      - ``None`` for HOLD
      - :class:`DryRunSkipped` when ``DRYRUN`` is not explicitly ``"false"``
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

    with IBKRClient(cfg) as client:
        current_pos = client.get_current_position(ib_symbol)
        if action == "BUY" and current_pos > 0:
            logger.warning(
                "Skipping BUY: already holding %d shares of %s", current_pos, ib_symbol
            )
            return OrderSkipped(signal=signal, ib_symbol=ib_symbol, reason="already_long")
        if action == "SELL" and current_pos == 0:
            logger.warning("Skipping SELL: no position in %s", ib_symbol)
            return OrderSkipped(signal=signal, ib_symbol=ib_symbol, reason="already_flat")
        trade = client.place_market_order(
            symbol=ib_symbol,
            quantity=quantity,
            action=action,
        )
    return trade
