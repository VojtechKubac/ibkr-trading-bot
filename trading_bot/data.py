from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class PriceDataConfig:
    """Default parameters for price data fetching."""

    symbol: str = "VWCE.DE"  # default to VWCE on XETRA
    # Default to ~5 years: typically enough for basic backtests across a few regimes
    # while keeping downloads fast. Some tickers (e.g. newer ETFs) simply won't have
    # 5 years of history available.
    lookback_days: int = 365 * 5
    interval: str = "1d"


def _default_start_end(lookback_days: int) -> tuple[date, date]:
    """Return (start, end) dates for the given number of lookback calendar days."""
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

    logger.debug("Fetching %s from %s to %s (interval=%s)", symbol, start, end, interval)
    ticker = yf.Ticker(symbol)
    hist = ticker.history(start=start, end=end, interval=interval, auto_adjust=False)

    if hist.empty:
        raise ValueError(f"No historical data returned for symbol {symbol!r}")

    logger.debug("Received %d rows for %s", len(hist), symbol)

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



def resample_ohlcv_weekly(df: pd.DataFrame, *, rule: str = "W-FRI") -> pd.DataFrame:
    """Resample a daily OHLCV DataFrame to weekly bars.

    The index is assumed to be datetime-like and sorted.

    Aggregation rules:

    - open: first
    - high: max
    - low: min
    - close: last
    - adj_close: last (if present)
    - volume: sum (if present)

    Args:
        df: Daily OHLCV data with columns using the project's lowercase schema.
        rule: Pandas resampling rule, defaulting to Friday-anchored weeks (W-FRI).

    Returns:
        Weekly OHLCV DataFrame.
    """

    if df.empty:
        return df.copy()

    cols = set(df.columns)
    agg: dict[str, str] = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "adj_close" in cols:
        agg["adj_close"] = "last"
    if "volume" in cols:
        agg["volume"] = "sum"

    out = df.resample(rule).agg(agg)
    # Drop weeks where we didn't get a close (e.g., leading partial week)
    out = out.dropna(subset=["close"]).sort_index()
    return out
