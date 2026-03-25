from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Optional

from ib_insync import IB, Contract, MarketOrder, Stock

logger = logging.getLogger(__name__)

Signal = Literal["BUY", "SELL", "HOLD"]


@dataclass
class IBKRConfig:
    """Connection parameters for TWS / IB Gateway."""

    host: str = "127.0.0.1"
    port: int = 7497  # default TWS paper trading port
    client_id: int = 1
    account: Optional[str] = None  # if None, let IBKR pick default
    exchange: str = "SMART"
    currency: str = "EUR"  # VWCE is EUR-denominated


class IBKRClient:
    """
    Thin wrapper around ib_insync for placing simple market orders.

    Intended to be used with TWS or IB Gateway running locally, ideally in
    paper trading mode first.
    """

    def __init__(self, cfg: IBKRConfig) -> None:
        self.cfg = cfg
        self.ib = IB()

    def __enter__(self) -> "IBKRClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()

    def connect(self) -> None:
        """Connect to TWS / IB Gateway."""
        if not self.ib.isConnected():
            logger.info("Connecting to IBKR at %s:%d (client_id=%d)", self.cfg.host, self.cfg.port, self.cfg.client_id)
            self.ib.connect(
                self.cfg.host,
                self.cfg.port,
                clientId=self.cfg.client_id,
            )

    def disconnect(self) -> None:
        """Disconnect from TWS / IB Gateway."""
        if self.ib.isConnected():
            logger.info("Disconnecting from IBKR")
            self.ib.disconnect()

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

    - BUY  -> BUY `quantity` shares
    - SELL -> SELL `quantity` shares
    - HOLD -> no order
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

    with IBKRClient(cfg) as client:
        trade = client.place_market_order(
            symbol=ib_symbol,
            quantity=quantity,
            action=action,
        )
    return trade

