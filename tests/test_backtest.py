from __future__ import annotations

import pandas as pd

from trading_bot.backtest import run_backtest_fixed_size


def _df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal enriched DataFrame from explicit per-row signal columns."""
    idx = pd.date_range("2020-01-01", periods=len(rows), freq="D")
    return pd.DataFrame(rows, index=idx)


def _buy_row(close: float) -> dict:
    """Row that triggers BUY: price > ma_long and price > ma_short."""
    return {"close": close, "ma_short": close * 0.9, "ma_long": close * 0.8, "rsi": 55.0}


def _sell_row(close: float) -> dict:
    """Row that triggers SELL: price < ma_long."""
    return {"close": close, "ma_short": close * 1.1, "ma_long": close * 1.2, "rsi": 45.0}


def _hold_row(close: float) -> dict:
    """Row that triggers HOLD: NaN MAs (window not filled)."""
    return {"close": close, "ma_short": float("nan"), "ma_long": float("nan"), "rsi": 50.0}


class TestRunBacktestFixedSize:
    def test_profitable_round_trip_increases_equity(self):
        """Equity grows when we buy at 50 and sell at 100."""
        df = _df([_buy_row(50.0), _sell_row(100.0)])
        result = run_backtest_fixed_size(df, initial_cash=10_000.0, position_size=1)
        assert result.equity_curve.iloc[-1] > result.equity_curve.iloc[0]

    def test_correct_trade_count(self):
        """One BUY + one SELL produces exactly two trade rows."""
        df = _df([_buy_row(100.0), _sell_row(80.0)])
        result = run_backtest_fixed_size(df, initial_cash=10_000.0, position_size=1)
        assert len(result.trades) == 2
        assert list(result.trades["side"]) == ["BUY", "SELL"]

    def test_total_return_formula(self):
        """total_return equals (final_equity / initial_cash) - 1."""
        df = _df([_buy_row(50.0), _sell_row(100.0)])
        initial = 10_000.0
        result = run_backtest_fixed_size(df, initial_cash=initial, position_size=1)
        expected = (result.equity_curve.iloc[-1] / initial) - 1.0
        assert abs(result.total_return - expected) < 1e-9

    def test_max_drawdown_is_nonpositive(self):
        """max_drawdown is always <= 0 by definition."""
        df = _df([_buy_row(100.0), _sell_row(80.0), _buy_row(90.0)])
        result = run_backtest_fixed_size(df, initial_cash=10_000.0, position_size=1)
        assert result.max_drawdown <= 0.0

    def test_no_buy_signal_zero_trades(self):
        """When no BUY ever fires the trades DataFrame is empty and return is 0."""
        df = _df([_hold_row(100.0), _hold_row(100.0), _hold_row(100.0)])
        result = run_backtest_fixed_size(df, initial_cash=10_000.0, position_size=1)
        assert result.trades.empty
        assert result.total_return == 0.0

    def test_sell_when_flat_produces_no_trade(self):
        """SELL signal when position is already 0 is silently ignored."""
        df = _df([_sell_row(80.0), _sell_row(70.0)])
        result = run_backtest_fixed_size(df, initial_cash=10_000.0, position_size=1)
        assert result.trades.empty

    def test_equity_curve_length_matches_input(self):
        """equity_curve has one entry per row in the input DataFrame."""
        df = _df([_hold_row(100.0)] * 10)
        result = run_backtest_fixed_size(df, initial_cash=10_000.0, position_size=1)
        assert len(result.equity_curve) == len(df)
