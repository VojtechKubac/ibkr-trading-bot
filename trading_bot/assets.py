from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class Asset:
    """
    Shared description of an asset across data and broker layers.

    - `yahoo_symbol` is used for price history via yfinance.
    - `ib_symbol` is used for order placement via IBKR.
    """

    name: str
    yahoo_symbol: str
    ib_symbol: str
    currency: str


# Initial small universe; extend this as the project grows.
#
# Key = short identifier used in CLI / configs.
ASSETS: Dict[str, Asset] = {
    "vwce": Asset(
        name="Vanguard FTSE All-World UCITS ETF",
        yahoo_symbol="VWCE.DE",
        ib_symbol="VWCE",
        currency="EUR",
    ),
    "spy": Asset(
        name="SPDR S&P 500 ETF Trust",
        yahoo_symbol="SPY",
        ib_symbol="SPY",
        currency="USD",
    ),
    "qqq": Asset(
        name="Invesco QQQ Trust",
        yahoo_symbol="QQQ",
        ib_symbol="QQQ",
        currency="USD",
    ),
    "vt": Asset(
        name="Vanguard Total World Stock ETF",
        yahoo_symbol="VT",
        ib_symbol="VT",
        currency="USD",
    ),
    "vea": Asset(
        name="Vanguard FTSE Developed Markets ETF",
        yahoo_symbol="VEA",
        ib_symbol="VEA",
        currency="USD",
    ),
    "vwo": Asset(
        name="Vanguard FTSE Emerging Markets ETF",
        yahoo_symbol="VWO",
        ib_symbol="VWO",
        currency="USD",
    ),
    "bnd": Asset(
        name="Vanguard Total Bond Market ETF",
        yahoo_symbol="BND",
        ib_symbol="BND",
        currency="USD",
    ),
    "agg": Asset(
        name="iShares Core U.S. Aggregate Bond ETF",
        yahoo_symbol="AGG",
        ib_symbol="AGG",
        currency="USD",
    ),
    "gld": Asset(
        name="SPDR Gold Shares",
        yahoo_symbol="GLD",
        ib_symbol="GLD",
        currency="USD",
    ),
    "eem": Asset(
        name="iShares MSCI Emerging Markets ETF",
        yahoo_symbol="EEM",
        ib_symbol="EEM",
        currency="USD",
    ),
}


def get_asset(key: str) -> Asset:
    try:
        return ASSETS[key.lower()]
    except KeyError as exc:
        raise KeyError(f"Unknown asset key {key!r}. Known keys: {', '.join(sorted(ASSETS))}") from exc

