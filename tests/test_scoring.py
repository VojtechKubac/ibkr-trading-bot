"""Tests for the weighted composite signal scoring engine."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from trading_bot.scoring import (
    ScoringConfig,
    _normalize_bb_position,
    _normalize_ma_trend,
    _normalize_macd_hist,
    _normalize_rsi,
    compute_composite_score,
    weighted_signal_for_row,
)


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

class TestNormalizeMaTrend:
    """Tests for _normalize_ma_trend."""

    def test_positive_when_price_above_ma(self):
        assert _normalize_ma_trend(110.0, 100.0) > 0.0

    def test_negative_when_price_below_ma(self):
        assert _normalize_ma_trend(90.0, 100.0) < 0.0

    def test_zero_when_price_equals_ma(self):
        assert _normalize_ma_trend(100.0, 100.0) == pytest.approx(0.0)

    def test_clipped_to_positive_one(self):
        assert _normalize_ma_trend(1000.0, 1.0) == pytest.approx(1.0)

    def test_clipped_to_negative_one(self):
        assert _normalize_ma_trend(0.001, 1000.0) == pytest.approx(-1.0, abs=1e-3)

    def test_zero_on_nan_ma(self):
        assert _normalize_ma_trend(100.0, float("nan")) == pytest.approx(0.0)

    def test_zero_on_zero_ma(self):
        assert _normalize_ma_trend(100.0, 0.0) == pytest.approx(0.0)


class TestNormalizeRsi:
    """Tests for _normalize_rsi."""

    def test_zero_at_rsi_50(self):
        assert _normalize_rsi(50.0) == pytest.approx(0.0)

    def test_positive_one_at_rsi_100(self):
        assert _normalize_rsi(100.0) == pytest.approx(1.0)

    def test_negative_one_at_rsi_0(self):
        assert _normalize_rsi(0.0) == pytest.approx(-1.0)

    def test_zero_on_nan(self):
        assert _normalize_rsi(float("nan")) == pytest.approx(0.0)


class TestNormalizeMacdHist:
    """Tests for _normalize_macd_hist."""

    def test_positive_for_positive_hist(self):
        assert _normalize_macd_hist(1.0) > 0.0

    def test_negative_for_negative_hist(self):
        assert _normalize_macd_hist(-1.0) < 0.0

    def test_zero_for_zero_hist(self):
        assert _normalize_macd_hist(0.0) == pytest.approx(0.0)

    def test_bounded_in_range(self):
        for v in (1e9, -1e9, 0.0001, -0.0001):
            result = _normalize_macd_hist(v)
            assert -1.0 <= result <= 1.0

    def test_zero_on_nan(self):
        assert _normalize_macd_hist(float("nan")) == pytest.approx(0.0)


class TestNormalizeBbPosition:
    """Tests for _normalize_bb_position."""

    def test_zero_at_midpoint(self):
        assert _normalize_bb_position(100.0, 110.0, 90.0) == pytest.approx(0.0)

    def test_positive_one_at_upper_band(self):
        assert _normalize_bb_position(110.0, 110.0, 90.0) == pytest.approx(1.0)

    def test_negative_one_at_lower_band(self):
        assert _normalize_bb_position(90.0, 110.0, 90.0) == pytest.approx(-1.0)

    def test_zero_on_nan_band(self):
        assert _normalize_bb_position(100.0, float("nan"), 90.0) == pytest.approx(0.0)

    def test_zero_on_zero_width_band(self):
        assert _normalize_bb_position(100.0, 100.0, 100.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_composite_score
# ---------------------------------------------------------------------------

class TestComputeCompositeScore:
    """Tests for composite score calculation."""

    def _bullish_row(self) -> pd.Series:
        """Row where all indicators agree bullishly."""
        return pd.Series({
            "close": 110.0, "ma_long": 90.0,   # price > ma_long
            "rsi": 70.0,                         # RSI above 50
            "macd_hist": 2.0,                    # positive histogram
            "bb_upper": 115.0, "bb_lower": 95.0, # price above midpoint
        })

    def _bearish_row(self) -> pd.Series:
        """Row where all indicators agree bearishly."""
        return pd.Series({
            "close": 85.0, "ma_long": 100.0,
            "rsi": 30.0,
            "macd_hist": -2.0,
            "bb_upper": 115.0, "bb_lower": 95.0,
        })

    def test_score_positive_for_bullish_row(self):
        assert compute_composite_score(self._bullish_row(), ScoringConfig()) > 0.0

    def test_score_negative_for_bearish_row(self):
        assert compute_composite_score(self._bearish_row(), ScoringConfig()) < 0.0

    def test_missing_phase2_columns_still_returns_float(self):
        """When MACD/BB columns are absent, score uses only MA trend and RSI."""
        row = pd.Series({"close": 110.0, "ma_long": 90.0, "rsi": 65.0})
        score = compute_composite_score(row, ScoringConfig())
        assert math.isfinite(score)

    def test_all_nan_returns_zero(self):
        row = pd.Series({"close": float("nan"), "ma_long": float("nan"), "rsi": float("nan")})
        assert compute_composite_score(row, ScoringConfig()) == pytest.approx(0.0)

    def test_zero_weights_returns_zero(self):
        cfg = ScoringConfig(weight_ma_trend=0.0, weight_rsi=0.0, weight_macd=0.0, weight_bb_position=0.0)
        row = pd.Series({"close": 110.0, "ma_long": 90.0, "rsi": 70.0})
        assert compute_composite_score(row, cfg) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# weighted_signal_for_row
# ---------------------------------------------------------------------------

class TestWeightedSignalForRow:
    """Tests for signal mapping from composite score."""

    def test_buy_signal_for_strongly_bullish_row(self):
        row = pd.Series({
            "close": 130.0, "ma_long": 90.0, "rsi": 75.0,
            "macd_hist": 3.0, "bb_upper": 135.0, "bb_lower": 100.0,
        })
        assert weighted_signal_for_row(row) == "BUY"

    def test_sell_signal_for_strongly_bearish_row(self):
        row = pd.Series({
            "close": 70.0, "ma_long": 100.0, "rsi": 25.0,
            "macd_hist": -3.0, "bb_upper": 110.0, "bb_lower": 90.0,
        })
        assert weighted_signal_for_row(row) == "SELL"

    def test_hold_signal_near_neutral(self):
        # Price just slightly above ma_long, neutral RSI → score near 0
        row = pd.Series({"close": 101.0, "ma_long": 100.0, "rsi": 50.0, "macd_hist": 0.0})
        assert weighted_signal_for_row(row) == "HOLD"

    def test_custom_thresholds_respected(self):
        cfg = ScoringConfig(buy_threshold=0.99, sell_threshold=-0.99)
        row = pd.Series({"close": 110.0, "ma_long": 90.0, "rsi": 70.0})
        # Score is positive but < 0.99 threshold → HOLD
        assert weighted_signal_for_row(row, cfg) == "HOLD"

    def test_default_config_used_when_none(self):
        row = pd.Series({"close": float("nan"), "ma_long": float("nan"), "rsi": float("nan")})
        assert weighted_signal_for_row(row) == "HOLD"
