from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.signals import (
    IndicatorConfig,
    compute_moving_averages,
    compute_rsi,
    enrich_with_indicators,
    latest_signal,
    rule_phase1_signal_for_row,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _price_series(n: int = 250, start: float = 100.0, step: float = 1.0) -> pd.Series:
    """Linearly increasing price series with a DatetimeIndex."""
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.Series([start + i * step for i in range(n)], index=idx, dtype=float)


def _ohlcv_df(prices: pd.Series, *, adj_close: pd.Series | None = None) -> pd.DataFrame:
    """Wrap a price series in a minimal OHLCV DataFrame."""
    df = pd.DataFrame({"close": prices}, index=prices.index)
    df["adj_close"] = adj_close if adj_close is not None else prices
    return df


# ---------------------------------------------------------------------------
# compute_moving_averages
# ---------------------------------------------------------------------------

class TestComputeMovingAverages:
    def test_nan_before_window_fills(self):
        prices = _price_series(50)
        window = 10
        ma = compute_moving_averages(prices, window)
        assert ma.iloc[: window - 1].isna().all()
        assert ma.iloc[window - 1 :].notna().all()

    def test_correct_value_at_window_boundary(self):
        # Constant prices → MA == price everywhere it is defined
        prices = pd.Series([5.0] * 20)
        ma = compute_moving_averages(prices, 5)
        assert ma.iloc[4] == pytest.approx(5.0)
        assert ma.iloc[-1] == pytest.approx(5.0)

    def test_manual_calculation(self):
        prices = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        ma = compute_moving_averages(prices, 3)
        assert ma.iloc[2] == pytest.approx(2.0)   # (1+2+3)/3
        assert ma.iloc[3] == pytest.approx(3.0)   # (2+3+4)/3
        assert ma.iloc[4] == pytest.approx(4.0)   # (3+4+5)/3


# ---------------------------------------------------------------------------
# compute_rsi
# ---------------------------------------------------------------------------

class TestComputeRsi:
    def test_rsi_values_in_range(self):
        """All non-NaN RSI values must lie in [0, 100]."""
        # Noisy series guarantees both gains and losses so we get non-NaN RSI values
        rng = np.random.default_rng(42)
        prices = _price_series(250) + pd.Series(
            rng.uniform(-2.0, 2.0, 250), index=pd.date_range("2020-01-01", periods=250, freq="D")
        )
        rsi = compute_rsi(prices)
        non_nan = rsi.dropna()
        assert len(non_nan) > 0
        assert (non_nan >= 0.0).all()
        assert (non_nan <= 100.0).all()

    def test_rsi_zero_for_all_losses(self):
        """Strictly decreasing prices → avg_gain == 0 → RSI == 0 after first delta."""
        # prices: 100, 99, 98, ... (constant step −1)
        prices = pd.Series([100.0 - i for i in range(50)])
        rsi = compute_rsi(prices, window=5)
        # Index 0: NaN (no prior delta); index 1 onward: RSI == 0
        assert pd.isna(rsi.iloc[0])
        assert rsi.iloc[1:].eq(0.0).all()

    def test_rsi_high_for_strong_gains(self):
        """Mostly rising prices → RSI should be high after warmup.

        A pure all-gains series makes avg_loss == 0, which the implementation
        maps to NaN (via replace(0, nan)).  To get a non-NaN high RSI we use a
        deterministic series with a tiny loss every 20 steps; the resulting
        avg_loss is small but non-zero, yielding RSI well above 90.
        """
        p = 100.0
        prices_list = []
        for i in range(250):
            if i % 20 == 0 and i > 0:
                p -= 0.01   # tiny loss; keeps avg_loss > 0
            else:
                p += 1.0    # large gain
            prices_list.append(p)
        prices = pd.Series(prices_list)
        rsi = compute_rsi(prices, window=14)
        # After sufficient warmup (50 bars) RSI should be consistently high
        assert rsi.iloc[50:].dropna().gt(90).all()

    def test_rsi_nan_at_index_zero(self):
        """RSI at index 0 is always NaN because prices.diff()[0] is NaN."""
        prices = _price_series(50)
        rsi = compute_rsi(prices)
        assert pd.isna(rsi.iloc[0])


# ---------------------------------------------------------------------------
# enrich_with_indicators
# ---------------------------------------------------------------------------

class TestEnrichWithIndicators:
    def test_output_columns_present(self):
        df = _ohlcv_df(_price_series(250))
        result = enrich_with_indicators(df)
        assert "ma_short" in result.columns
        assert "ma_long" in result.columns
        assert "rsi" in result.columns

    def test_uses_adj_close_when_available(self):
        prices = _price_series(250)
        adj = prices * 0.9   # deliberately different from close
        df = _ohlcv_df(prices, adj_close=adj)
        cfg = IndicatorConfig(short_ma_window=50, long_ma_window=200)
        result = enrich_with_indicators(df, cfg)
        expected_ma = compute_moving_averages(adj, 50)
        pd.testing.assert_series_equal(result["ma_short"], expected_ma, check_names=False)

    def test_falls_back_to_close_when_adj_close_is_nan(self):
        """When adj_close is all-NaN, fillna falls back to close."""
        prices = _price_series(250)
        nan_adj = pd.Series([float("nan")] * 250, index=prices.index)
        df = _ohlcv_df(prices, adj_close=nan_adj)
        cfg = IndicatorConfig(short_ma_window=50, long_ma_window=200)
        result = enrich_with_indicators(df, cfg)
        expected_ma = compute_moving_averages(prices, 50)
        pd.testing.assert_series_equal(result["ma_short"], expected_ma, check_names=False)

    def test_does_not_mutate_input(self):
        df = _ohlcv_df(_price_series(250))
        original_cols = set(df.columns)
        enrich_with_indicators(df)
        assert set(df.columns) == original_cols


# ---------------------------------------------------------------------------
# rule_phase1_signal_for_row
# ---------------------------------------------------------------------------

class TestRulePhase1SignalForRow:
    def _row(self, price: float, ma_short: float, ma_long: float) -> pd.Series:
        return pd.Series({"close": price, "ma_short": ma_short, "ma_long": ma_long})

    def test_buy_when_price_above_both_mas(self):
        assert rule_phase1_signal_for_row(self._row(110, 100, 90)) == "BUY"

    def test_sell_when_price_below_ma_long(self):
        assert rule_phase1_signal_for_row(self._row(80, 90, 85)) == "SELL"

    def test_hold_when_above_ma_long_but_below_ma_short(self):
        # price > ma_long (90) but price < ma_short (100)
        assert rule_phase1_signal_for_row(self._row(95, 100, 90)) == "HOLD"

    def test_hold_when_ma_is_nan(self):
        assert rule_phase1_signal_for_row(self._row(100, float("nan"), float("nan"))) == "HOLD"


# ---------------------------------------------------------------------------
# latest_signal
# ---------------------------------------------------------------------------

class TestLatestSignal:
    def _df(self, price: float, ma_short: float, ma_long: float) -> pd.DataFrame:
        n = 5
        idx = pd.date_range("2020-01-01", periods=n, freq="D")
        return pd.DataFrame(
            {
                "close": [100.0] * (n - 1) + [price],
                "ma_short": [100.0] * (n - 1) + [ma_short],
                "ma_long": [100.0] * (n - 1) + [ma_long],
                "rsi": [50.0] * n,
            },
            index=idx,
        )

    def test_returns_last_row_timestamp(self):
        df = self._df(price=110, ma_short=100, ma_long=90)
        ts, _, _ = latest_signal(df)
        assert ts == df.index[-1]

    def test_returns_buy_signal(self):
        _, sig, _ = latest_signal(self._df(price=110, ma_short=100, ma_long=90))
        assert sig == "BUY"

    def test_returns_sell_signal(self):
        _, sig, _ = latest_signal(self._df(price=80, ma_short=90, ma_long=85))
        assert sig == "SELL"

    def test_returns_last_row_series(self):
        df = self._df(price=110, ma_short=100, ma_long=90)
        _, _, row = latest_signal(df)
        pd.testing.assert_series_equal(row, df.iloc[-1])
