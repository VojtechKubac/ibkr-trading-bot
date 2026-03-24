from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from ib_insync import IB, Contract, MarketOrder, Stock

from trading_bot import config

Signal = Literal["BUY", "SELL", "HOLD"]


@dataclass
class IBKRConfig:
    host: str = config.IBKR_HOST
    port: int = config.IBKR_PORT
    client_id: int = config.IBKR_CLIENT_ID
    account: Optional[str] = config.IBKR_ACCOUNT
    exchange: str = "SMART"
    currency: str = config.IBKR_CURRENCY


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
        if not self.ib.isConnected():
            self.ib.connect(
                self.cfg.host,
                self.cfg.port,
                clientId=self.cfg.client_id,
            )

    def disconnect(self) -> None:
        if self.ib.isConnected():
            self.ib.disconnect()

    def _build_stock_contract(self, symbol: str) -> Contract:
        return Stock(symbol, self.cfg.exchange, self.cfg.currency)

    def place_market_order(
        self,
        symbol: str,
        quantity: int,
        action: Literal["BUY", "SELL"],
    ):
        if quantity <= 0:
            raise ValueError("Quantity must be positive for a market order.")

        contract = self._build_stock_contract(symbol)
        order = MarketOrder(action, quantity)
        trade = self.ib.placeOrder(contract, order)
        # Give IBKR a small moment to process the order so status is populated.
        self.ib.sleep(0.5)
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

