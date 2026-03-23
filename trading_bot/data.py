from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf


@dataclass
class PriceDataConfig:
    symbol: str = "VWCE.DE"  # default to VWCE on XETRA
    # Default to ~5 years: typically enough for basic backtests across a few regimes
    # while keeping downloads fast. Some tickers (e.g. newer ETFs) simply won't have
    # 5 years of history available.
    lookback_days: int = 365 * 5
    interval: str = "1d"


def _default_start_end(lookback_days: int) -> tuple[date, date]:
    end = date.today()
    start = end - timedelta(days=lookback_days)
    return start, end


def fetch_ohlcv(
    symbol: str,
    lookback_days: int = 365 * 5,
    interval: str = "1d",
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> pd.DataFrame:
    """
    Fetch OHLCV data for a symbol using Yahoo Finance via yfinance.

    Returns a DataFrame indexed by datetime with at least columns:
    ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume'].
    """
    if start is None or end is None:
        start, end = _default_start_end(lookback_days)

    ticker = yf.Ticker(symbol)
    hist = ticker.history(start=start, end=end, interval=interval, auto_adjust=False)

    if hist.empty:
        raise ValueError(f"No historical data returned for symbol {symbol!r}")

    # Normalise column names to a consistent schema
    hist = hist.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )

    # Ensure datetime index is sorted and has no duplicate entries
    hist = hist.sort_index().loc[~hist.index.duplicated(keep="last")]

    return hist

