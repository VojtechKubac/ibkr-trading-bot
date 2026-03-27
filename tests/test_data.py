from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from trading_bot.data import fetch_ohlcv, resample_ohlcv_weekly


def _make_raw_df(n: int = 5, *, duplicate_last: bool = False) -> pd.DataFrame:
    """Build a synthetic raw yfinance DataFrame with proper column names."""
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    df = pd.DataFrame(
        {
            "Open": [100.0 + i for i in range(n)],
            "High": [105.0 + i for i in range(n)],
            "Low": [95.0 + i for i in range(n)],
            "Close": [102.0 + i for i in range(n)],
            "Adj Close": [101.0 + i for i in range(n)],
            "Volume": [1_000 * (i + 1) for i in range(n)],
        },
        index=idx,
    )
    if duplicate_last:
        df = pd.concat([df, df.iloc[[-1]]])
    return df


class TestFetchOhlcv:
    def _mock_ticker(self, df: pd.DataFrame) -> MagicMock:
        """Return a mock yf.Ticker whose .history() returns df."""
        ticker = MagicMock()
        ticker.history.return_value = df
        return ticker

    def test_returns_lowercase_columns(self):
        """fetch_ohlcv renames raw yfinance columns to lowercase snake_case."""
        with patch("trading_bot.data.yf.Ticker") as MockTicker:
            MockTicker.return_value = self._mock_ticker(_make_raw_df())
            df = fetch_ohlcv("VWCE.DE", start=date(2020, 1, 1), end=date(2020, 1, 6))

        assert set(df.columns) >= {"open", "high", "low", "close", "adj_close", "volume"}
        assert "Open" not in df.columns

    def test_raises_value_error_on_empty_response(self):
        """fetch_ohlcv raises ValueError when yfinance returns an empty DataFrame."""
        empty = pd.DataFrame()
        with patch("trading_bot.data.yf.Ticker") as MockTicker:
            MockTicker.return_value = self._mock_ticker(empty)
            with pytest.raises(ValueError, match="No historical data"):
                fetch_ohlcv("INVALID", start=date(2020, 1, 1), end=date(2020, 1, 6))

    def test_index_is_sorted_ascending(self):
        """The returned DataFrame index is sorted in ascending order."""
        raw = _make_raw_df(5)
        shuffled = raw.iloc[::-1]  # reverse the order
        with patch("trading_bot.data.yf.Ticker") as MockTicker:
            MockTicker.return_value = self._mock_ticker(shuffled)
            df = fetch_ohlcv("VWCE.DE", start=date(2020, 1, 1), end=date(2020, 1, 6))

        assert df.index.is_monotonic_increasing

    def test_no_duplicate_timestamps(self):
        """Duplicate index entries are deduplicated (last value kept)."""
        raw_with_dup = _make_raw_df(5, duplicate_last=True)
        with patch("trading_bot.data.yf.Ticker") as MockTicker:
            MockTicker.return_value = self._mock_ticker(raw_with_dup)
            df = fetch_ohlcv("VWCE.DE", start=date(2020, 1, 1), end=date(2020, 1, 6))

        assert df.index.is_unique



def test_resample_ohlcv_weekly_aggregates_to_friday_close():
    idx = pd.date_range("2020-01-06", periods=10, freq="B", tz="UTC")  # Mon..Fri x2
    df = pd.DataFrame(
        {
            "open": [100 + i for i in range(len(idx))],
            "high": [110 + i for i in range(len(idx))],
            "low": [90 + i for i in range(len(idx))],
            "close": [105 + i for i in range(len(idx))],
            "adj_close": [104 + i for i in range(len(idx))],
            "volume": [1000 for _ in range(len(idx))],
        },
        index=idx,
    )

    weekly = resample_ohlcv_weekly(df)

    assert list(weekly.index.strftime("%Y-%m-%d")) == ["2020-01-10", "2020-01-17"]

    # First week open is first bar, close is Friday bar
    assert weekly.iloc[0]["open"] == 100
    assert weekly.iloc[0]["close"] == 105 + 4
    assert weekly.iloc[0]["high"] == 110 + 4
    assert weekly.iloc[0]["low"] == 90
    assert weekly.iloc[0]["volume"] == 5 * 1000

    # Second week close uses the last business day (Fri)
    assert weekly.iloc[1]["open"] == 100 + 5
    assert weekly.iloc[1]["close"] == 105 + 9
