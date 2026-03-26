"""Weighted composite signal scoring engine (Phase 2).

Each available indicator is normalised to a [-1, +1] scale where +1 is
maximally bullish and -1 is maximally bearish.  The scores are combined via
configurable weights and mapped to a BUY/HOLD/SELL signal through configurable
thresholds.

Missing or NaN indicators contribute 0 (neutral) so the engine degrades
gracefully when Phase 2 columns are absent from the DataFrame.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from trading_bot.signals import Signal


@dataclass
class ScoringConfig:
    """Weights and thresholds for the composite scoring engine.

    All weights are non-negative; they are normalised internally so they do not
    need to sum to 1.  Indicators with NaN values contribute 0 to the sum.
    """

    weight_ma_trend: float = 0.40     # price position relative to long MA
    weight_rsi: float = 0.30          # RSI centred on 50
    weight_macd: float = 0.20         # MACD histogram direction/magnitude
    weight_bb_position: float = 0.10  # price position within Bollinger Bands

    buy_threshold: float = 0.20       # composite score > this → BUY
    sell_threshold: float = -0.20     # composite score < this → SELL

    def __post_init__(self) -> None:
        weights = (
            self.weight_ma_trend,
            self.weight_rsi,
            self.weight_macd,
            self.weight_bb_position,
        )
        if any(w < 0.0 for w in weights):
            raise ValueError("Scoring weights must be non-negative.")
        if sum(weights) <= 0.0:
            raise ValueError("Sum of scoring weights must be greater than zero.")
        if self.buy_threshold <= self.sell_threshold:
            raise ValueError("buy_threshold must be greater than sell_threshold.")


# ---------------------------------------------------------------------------
# Normalisation helpers — each returns a value in [-1, +1] or 0.0 on NaN
# ---------------------------------------------------------------------------

def _normalize_ma_trend(price: float, ma_long: float) -> float:
    """(price − ma_long) / ma_long, clipped to [-1, +1].

    Returns 0 when ma_long is NaN or zero.
    """
    if not math.isfinite(price) or not math.isfinite(ma_long) or ma_long == 0.0:
        return 0.0
    return max(-1.0, min(1.0, (price - ma_long) / ma_long))


def _normalize_rsi(rsi: float) -> float:
    """(rsi − 50) / 50, clipped to [-1, +1].

    Returns 0 when rsi is NaN.
    """
    if not math.isfinite(rsi):
        return 0.0
    return max(-1.0, min(1.0, (rsi - 50.0) / 50.0))


def _normalize_macd_hist(macd_hist: float, scale: float = 1.0) -> float:
    """tanh(macd_hist / scale) — smooth [-1, +1] representation of histogram.

    Returns 0 when macd_hist is NaN or scale is zero.
    """
    if not math.isfinite(macd_hist) or scale == 0.0:
        return 0.0
    return math.tanh(macd_hist / scale)


def _normalize_bb_position(price: float, bb_upper: float, bb_lower: float) -> float:
    """Price position within the Bollinger Band, mapped to [-1, +1].

    0 at the midpoint, +1 at or above the upper band, -1 at or below the lower.
    Returns 0 when any band value is NaN or the band has zero width.
    """
    if not all(math.isfinite(v) for v in (price, bb_upper, bb_lower)):
        return 0.0
    band_width = bb_upper - bb_lower
    if band_width == 0.0:
        return 0.0
    mid = (bb_upper + bb_lower) / 2.0
    return max(-1.0, min(1.0, 2.0 * (price - mid) / band_width))


# ---------------------------------------------------------------------------
# Composite score and signal
# ---------------------------------------------------------------------------

def compute_composite_score(row: pd.Series, cfg: ScoringConfig) -> float:
    """Compute the weighted composite score for a single bar.

    Returns a value roughly in [-1, +1]; sign indicates bullish (positive) or
    bearish (negative) bias.  NaN indicators contribute a neutral 0.
    """
    total_weight = (
        cfg.weight_ma_trend + cfg.weight_rsi + cfg.weight_macd + cfg.weight_bb_position
    )
    if total_weight == 0.0:
        return 0.0

    score = (
        cfg.weight_ma_trend   * _normalize_ma_trend(float(row.get("close", float("nan"))),
                                                      float(row.get("ma_long", float("nan"))))
        + cfg.weight_rsi      * _normalize_rsi(float(row.get("rsi", float("nan"))))
        + cfg.weight_macd     * _normalize_macd_hist(float(row.get("macd_hist", float("nan"))))
        + cfg.weight_bb_position * _normalize_bb_position(
            float(row.get("close", float("nan"))),
            float(row.get("bb_upper", float("nan"))),
            float(row.get("bb_lower", float("nan"))),
        )
    )
    return score / total_weight


def weighted_signal_for_row(row: pd.Series, cfg: ScoringConfig | None = None) -> Signal:
    """Return BUY/HOLD/SELL for a single bar using the composite scoring engine.

    Args:
        row: A pandas Series representing one bar with precomputed indicator columns.
        cfg: Scoring configuration; uses defaults when None.
    """
    if cfg is None:
        cfg = ScoringConfig()
    score = compute_composite_score(row, cfg)
    if score > cfg.buy_threshold:
        return "BUY"
    if score < cfg.sell_threshold:
        return "SELL"
    return "HOLD"
