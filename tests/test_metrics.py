from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.metrics import build_performance_report


def test_cagr_matches_definition_over_datetime_index():
    idx = pd.to_datetime(["2020-01-01", "2021-01-01"])
    equity = pd.Series([100.0, 110.0], index=idx, name="equity")
    report = build_performance_report(equity_curve=equity, trades=pd.DataFrame(), position_curve=None)

    years = (idx[-1] - idx[0]).total_seconds() / (24 * 3600) / 365.25
    expected = (110.0 / 100.0) ** (1.0 / years) - 1.0
    assert report.cagr == pytest.approx(expected)


def test_trade_and_exposure_metrics_are_computed():
    idx = pd.date_range("2020-01-01", periods=4, freq="D")
    equity = pd.Series([100.0, 100.0, 110.0, 110.0], index=idx, name="equity")
    position = pd.Series([0, 1, 1, 0], index=idx, name="position")

    trades = pd.DataFrame(
        [
            {"timestamp": idx[1], "side": "BUY", "price": 100.0, "size": 1, "commission": 1.0, "stop_loss": False},
            {"timestamp": idx[3], "side": "SELL", "price": 120.0, "size": 1, "commission": 1.0, "stop_loss": False},
        ]
    )

    report = build_performance_report(equity_curve=equity, trades=trades, position_curve=position)

    assert report.trade_round_trips == 1
    assert report.win_rate == pytest.approx(1.0)
    # pnl = (1*120 - 1 commission) - (1*100 + 1 commission) = 18
    assert report.avg_win == pytest.approx(18.0)
    assert report.avg_loss is None
    assert report.expectancy == pytest.approx(18.0)

    # exposure = 2/4 bars in market
    assert report.exposure == pytest.approx(0.5)

    # turnover = sum(|size*price|) / avg_equity = (100+120) / 105
    assert report.turnover == pytest.approx((220.0) / 105.0)


def test_sharpe_is_none_when_volatility_is_zero():
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    # Constant equity -> returns are exactly zero -> volatility is zero.
    equity = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    report = build_performance_report(equity_curve=equity, trades=pd.DataFrame(), position_curve=None)

    assert report.annualized_volatility == 0.0
    assert report.sharpe is None
