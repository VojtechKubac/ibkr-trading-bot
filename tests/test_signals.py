from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.signals import (
    IndicatorConfig,
    compute_bollinger_bands,
    compute_macd,
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
        """First window-1 values are NaN; all values from index window-1 onward are finite."""
        prices = _price_series(50)
        window = 10
        ma = compute_moving_averages(prices, window)
        assert ma.iloc[: window - 1].isna().all()
        assert ma.iloc[window - 1 :].notna().all()

    def test_correct_value_at_window_boundary(self):
        """Constant price series produces MA equal to that price at and after the window boundary."""
        # Constant prices → MA == price everywhere it is defined
        prices = pd.Series([5.0] * 20)
        ma = compute_moving_averages(prices, 5)
        assert ma.iloc[4] == pytest.approx(5.0)
        assert ma.iloc[-1] == pytest.approx(5.0)

    def test_manual_calculation(self):
        """MA values match hand-calculated rolling means for a known input sequence."""
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
        # prices: 100, 99, 98, ... (constant step -1)
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

# ---------------------------------------------------------------------------
# compute_macd
# ---------------------------------------------------------------------------

class TestComputeMacd:
    """Tests for the MACD indicator."""

    def test_returns_three_columns(self):
        """compute_macd returns a DataFrame with exactly macd, macd_signal, macd_hist."""
        prices = _price_series(100)
        result = compute_macd(prices)
        assert set(result.columns) == {"macd", "macd_signal", "macd_hist"}

    def test_histogram_equals_macd_minus_signal(self):
        """macd_hist == macd − macd_signal at every row."""
        prices = _price_series(100)
        result = compute_macd(prices)
        diff = result["macd"] - result["macd_signal"]
        pd.testing.assert_series_equal(result["macd_hist"], diff, check_names=False, atol=1e-10)

    def test_values_finite_after_warmup(self):
        """All three columns are finite for every row (EWM starts immediately)."""
        prices = _price_series(100)
        result = compute_macd(prices, fast=12, slow=26, signal_window=9)
        assert result.notna().all().all()

    def test_macd_zero_for_constant_prices(self):
        """Constant prices → EMA_fast == EMA_slow → MACD == 0 everywhere."""
        prices = pd.Series([50.0] * 50)
        result = compute_macd(prices)
        assert result["macd"].abs().max() == pytest.approx(0.0, abs=1e-10)

    def test_index_preserved(self):
        """Output index matches the input Series index."""
        prices = _price_series(60)
        result = compute_macd(prices)
        pd.testing.assert_index_equal(result.index, prices.index)


# ---------------------------------------------------------------------------
# compute_bollinger_bands
# ---------------------------------------------------------------------------

class TestComputeBollingerBands:
    """Tests for Bollinger Bands."""

    def test_returns_three_columns(self):
        """Returns a DataFrame with bb_upper, bb_middle, bb_lower."""
        prices = _price_series(50)
        result = compute_bollinger_bands(prices, window=10)
        assert set(result.columns) == {"bb_upper", "bb_middle", "bb_lower"}

    def test_nan_before_window_fills(self):
        """Rows before the window is full are NaN."""
        prices = _price_series(30)
        result = compute_bollinger_bands(prices, window=20)
        assert result.iloc[:19].isna().all().all()
        assert result.iloc[19:].notna().all().all()

    def test_upper_above_middle_above_lower(self):
        """upper > middle > lower for all non-NaN rows when prices are not constant."""
        prices = _price_series(50, step=1.0)
        result = compute_bollinger_bands(prices, window=10)
        valid = result.dropna()
        assert (valid["bb_upper"] > valid["bb_middle"]).all()
        assert (valid["bb_middle"] > valid["bb_lower"]).all()

    def test_middle_equals_rolling_mean(self):
        """bb_middle matches pandas rolling mean independently."""
        prices = _price_series(50)
        result = compute_bollinger_bands(prices, window=10)
        expected_middle = prices.rolling(window=10, min_periods=10).mean()
        pd.testing.assert_series_equal(result["bb_middle"], expected_middle, check_names=False)

    def test_bands_symmetric_around_middle(self):
        """upper − middle == middle − lower at every non-NaN row."""
        prices = _price_series(50)
        result = compute_bollinger_bands(prices, window=10).dropna()
        upper_dist = result["bb_upper"] - result["bb_middle"]
        lower_dist = result["bb_middle"] - result["bb_lower"]
        pd.testing.assert_series_equal(upper_dist, lower_dist, check_names=False, atol=1e-10)

    def test_constant_prices_zero_width(self):
        """Constant prices → std == 0 → all three bands collapse to the same value."""
        prices = pd.Series([100.0] * 30)
        result = compute_bollinger_bands(prices, window=10).dropna()
        assert (result["bb_upper"] == result["bb_lower"]).all()


# ---------------------------------------------------------------------------
# enrich_with_indicators
# ---------------------------------------------------------------------------

class TestEnrichWithIndicators:
    def test_output_columns_present(self):
        """Result DataFrame contains Phase 1 and Phase 2 indicator columns."""
        df = _ohlcv_df(_price_series(250))
        result = enrich_with_indicators(df)
        for col in ("ma_short", "ma_long", "rsi", "macd", "macd_signal", "macd_hist",
                    "bb_upper", "bb_middle", "bb_lower"):
            assert col in result.columns, f"Missing column: {col}"

    def test_uses_adj_close_when_available(self):
        """Indicators are computed from adj_close when it contains non-NaN values."""
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
        """enrich_with_indicators must not alter the caller's DataFrame in any way."""
        df = _ohlcv_df(_price_series(250))
        original = df.copy(deep=True)
        enrich_with_indicators(df)
        pd.testing.assert_frame_equal(df, original)


# ---------------------------------------------------------------------------
# rule_phase1_signal_for_row
# ---------------------------------------------------------------------------

class TestRulePhase1SignalForRow:
    def _row(self, price: float, ma_short: float, ma_long: float) -> pd.Series:
        """Build a minimal row Series with the three columns the rule function reads."""
        return pd.Series({"close": price, "ma_short": ma_short, "ma_long": ma_long})

    def test_buy_when_price_above_both_mas(self):
        """BUY when price is above both the short and long moving averages."""
        assert rule_phase1_signal_for_row(self._row(110, 100, 90)) == "BUY"

    def test_sell_when_price_below_ma_long(self):
        """SELL when price falls below the long moving average."""
        assert rule_phase1_signal_for_row(self._row(80, 90, 85)) == "SELL"

    def test_hold_when_above_ma_long_but_below_ma_short(self):
        """HOLD when price is above the long MA but still below the short MA."""
        # price > ma_long (90) but price < ma_short (100)
        assert rule_phase1_signal_for_row(self._row(95, 100, 90)) == "HOLD"

    def test_hold_when_ma_is_nan(self):
        """HOLD when either MA is NaN (window not yet filled)."""
        assert rule_phase1_signal_for_row(self._row(100, float("nan"), float("nan"))) == "HOLD"


# ---------------------------------------------------------------------------
# latest_signal
# ---------------------------------------------------------------------------

class TestLatestSignal:
    def _df(self, price: float, ma_short: float, ma_long: float) -> pd.DataFrame:
        """Build a 5-row DataFrame where only the last row has the given signal values."""
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
        """latest_signal returns the index timestamp of the final row."""
        df = self._df(price=110, ma_short=100, ma_long=90)
        ts, _, _ = latest_signal(df)
        assert ts == df.index[-1]

    def test_returns_buy_signal(self):
        """latest_signal returns BUY when the last row satisfies the BUY conditions."""
        _, sig, _ = latest_signal(self._df(price=110, ma_short=100, ma_long=90))
        assert sig == "BUY"

    def test_returns_sell_signal(self):
        """latest_signal returns SELL when the last row satisfies the SELL conditions."""
        _, sig, _ = latest_signal(self._df(price=80, ma_short=90, ma_long=85))
        assert sig == "SELL"

    def test_returns_last_row_series(self):
        """latest_signal returns the actual last row Series unchanged."""
        df = self._df(price=110, ma_short=100, ma_long=90)
        _, _, row = latest_signal(df)
        pd.testing.assert_series_equal(row, df.iloc[-1])
