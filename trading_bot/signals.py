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
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_window: int = 20
    bb_num_std: float = 2.0


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


def compute_macd(
    prices: pd.Series,
    *,
    fast: int = 12,
    slow: int = 26,
    signal_window: int = 9,
) -> pd.DataFrame:
    """MACD line (fast EMA − slow EMA), signal line, and histogram.

    Returns a DataFrame with columns ``macd``, ``macd_signal``, ``macd_hist``.
    Early rows contain NaN while the slow EMA window fills.
    """
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_window, adjust=False).mean()
    return pd.DataFrame(
        {"macd": macd_line, "macd_signal": signal_line, "macd_hist": macd_line - signal_line},
        index=prices.index,
    )


def compute_bollinger_bands(
    prices: pd.Series,
    *,
    window: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    """Bollinger Bands: middle SMA ± num_std rolling standard deviations.

    Returns a DataFrame with columns ``bb_upper``, ``bb_middle``, ``bb_lower``.
    Rows with fewer than ``window`` observations are NaN.
    """
    middle = prices.rolling(window=window, min_periods=window).mean()
    std = prices.rolling(window=window, min_periods=window).std(ddof=1)
    return pd.DataFrame(
        {"bb_upper": middle + num_std * std, "bb_middle": middle, "bb_lower": middle - num_std * std},
        index=prices.index,
    )


def enrich_with_indicators(
    df: pd.DataFrame,
    cfg: IndicatorConfig | None = None,
) -> pd.DataFrame:
    """
    Add MA, RSI, MACD, and Bollinger Band columns to the OHLCV DataFrame.
    """
    if cfg is None:
        cfg = IndicatorConfig()

    close = df["adj_close"].fillna(df["close"])

    df = df.copy()
    df["ma_short"] = compute_moving_averages(close, cfg.short_ma_window)
    df["ma_long"] = compute_moving_averages(close, cfg.long_ma_window)
    df["rsi"] = compute_rsi(close, cfg.rsi_window)

    macd_df = compute_macd(close, fast=cfg.macd_fast, slow=cfg.macd_slow, signal_window=cfg.macd_signal)
    df[["macd", "macd_signal", "macd_hist"]] = macd_df

    bb_df = compute_bollinger_bands(close, window=cfg.bb_window, num_std=cfg.bb_num_std)
    df[["bb_upper", "bb_middle", "bb_lower"]] = bb_df

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

