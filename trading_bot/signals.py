from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


Signal = Literal["BUY", "SELL", "HOLD"]


@dataclass
class IndicatorConfig:
    """Configuration for technical indicator parameters."""

    short_ma_window: int = 50
    long_ma_window: int = 200
    rsi_window: int = 14


def compute_moving_averages(
    prices: pd.Series,
    window: int,
) -> pd.Series:
    """
    Simple moving average.
    """
    return prices.rolling(window=window, min_periods=window).mean()


def compute_rsi(
    prices: pd.Series,
    window: int = 14,
) -> pd.Series:
    """
    Compute a classic Wilder-style RSI.
    """
    delta = prices.diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    gain_series = pd.Series(gain, index=prices.index)
    loss_series = pd.Series(loss, index=prices.index)

    avg_gain = gain_series.ewm(alpha=1 / window, adjust=False).mean()
    avg_loss = loss_series.ewm(alpha=1 / window, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def enrich_with_indicators(
    df: pd.DataFrame,
    cfg: IndicatorConfig | None = None,
) -> pd.DataFrame:
    """
    Add MA and RSI columns to the OHLCV DataFrame.
    """
    if cfg is None:
        cfg = IndicatorConfig()

    close = df["adj_close"].fillna(df["close"])

    df = df.copy()
    df["ma_short"] = compute_moving_averages(close, cfg.short_ma_window)
    df["ma_long"] = compute_moving_averages(close, cfg.long_ma_window)
    df["rsi"] = compute_rsi(close, cfg.rsi_window)
    return df


def rule_phase1_signal_for_row(row: pd.Series) -> Signal:
    """
    Apply the Phase 1 example rule set for a single bar.

    Assumes columns: close, ma_short, ma_long.
    RSI is currently computed but not used in the rules yet.
    """
    price = row["close"]
    ma_short = row["ma_short"]
    ma_long = row["ma_long"]

    if pd.isna(ma_short) or pd.isna(ma_long):
        return "HOLD"

    if price > ma_long and price > ma_short:
        return "BUY"
    if price < ma_long:
        return "SELL"
    # price > ma_long but price < ma_short
    return "HOLD"


def latest_signal(df_with_indicators: pd.DataFrame) -> tuple[pd.Timestamp, Signal, pd.Series]:
    """
    Compute the Phase 1 signal for the most recent available bar.
    """
    last_row = df_with_indicators.iloc[-1]
    ts = df_with_indicators.index[-1]
    sig = rule_phase1_signal_for_row(last_row)
    logger.debug("Latest signal: %s at %s", sig, ts)
    return ts, sig, last_row

