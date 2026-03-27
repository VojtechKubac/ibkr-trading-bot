from __future__ import annotations

import pandas as pd

from trading_bot.data import resample_ohlcv_weekly
from trading_bot.signals import IndicatorConfig, enrich_with_indicators, latest_signal


def test_weekly_resample_then_signal_generation_is_deterministic():
    idx = pd.date_range("2020-01-06", periods=20, freq="B", tz="UTC")  # 4 weeks
    close = [100 + i for i in range(len(idx))]
    df = pd.DataFrame(
        {
            "open": close,
            "high": [c + 1 for c in close],
            "low": [c - 1 for c in close],
            "close": close,
            "adj_close": close,
            "volume": [1000 for _ in close],
        },
        index=idx,
    )

    weekly = resample_ohlcv_weekly(df)
    df_ind = enrich_with_indicators(weekly, IndicatorConfig(short_ma_window=2, long_ma_window=3, rsi_window=2))
    _, sig, _ = latest_signal(df_ind)

    # With monotonic weekly closes and small MA windows, we should end in BUY.
    assert sig == "BUY"
