from __future__ import annotations

import pytest
import pandas as pd

from trading_bot.backtest import BacktestConfig, run_backtest, run_backtest_fixed_size


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
        assert result.total_return == pytest.approx(0.0)

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

    def test_alias_backward_compat(self):
        """run_backtest_fixed_size alias produces identical results to run_backtest with same config."""
        df = _df([_buy_row(50.0), _sell_row(100.0)])
        alias = run_backtest_fixed_size(df, initial_cash=10_000.0, position_size=1)
        direct = run_backtest(df, cfg=BacktestConfig(initial_cash=10_000.0, position_size=1))
        assert alias.total_return == pytest.approx(direct.total_return)
        assert alias.commission_paid == pytest.approx(direct.commission_paid)


class TestCommission:
    """Tests that commission costs are correctly deducted on trades."""

    def test_commission_deducted_on_buy_and_sell(self):
        """commission_paid > 0 when at least one round-trip trade occurs."""
        df = _df([_buy_row(100.0), _sell_row(200.0)])
        result = run_backtest(
            df, cfg=BacktestConfig(initial_cash=10_000.0, commission_pct=0.001, commission_min=1.0)
        )
        assert result.commission_paid > 0.0

    def test_commission_lowers_equity_vs_zero_commission(self):
        """Final equity is lower when commission is applied than when it is zero."""
        df = _df([_buy_row(100.0), _sell_row(200.0)])
        no_comm = run_backtest(df, cfg=BacktestConfig(commission_pct=0.0, commission_min=0.0))
        with_comm = run_backtest(df, cfg=BacktestConfig(commission_pct=0.001, commission_min=1.0))
        assert with_comm.equity_curve.iloc[-1] < no_comm.equity_curve.iloc[-1]

    def test_minimum_commission_applied(self):
        """Commission equals commission_min when pct * value < commission_min."""
        # trade value = 1 share * 1.0 = 1.0, pct commission = 0.001 * 1.0 = 0.001 < min 1.0
        df = _df([_buy_row(1.0), _sell_row(2.0)])
        result = run_backtest(
            df, cfg=BacktestConfig(initial_cash=10_000.0, commission_pct=0.001, commission_min=1.0)
        )
        # Both BUY and SELL should each cost at least 1.0
        assert result.commission_paid >= 2.0

    def test_no_commission_on_zero_trades(self):
        """commission_paid is 0 when no trades execute."""
        df = _df([_hold_row(100.0)] * 5)
        result = run_backtest(df, cfg=BacktestConfig())
        assert result.commission_paid == pytest.approx(0.0)


class TestStopLoss:
    """Tests that the backtest stop-loss fires correctly."""

    def test_stop_loss_triggers_sell_before_signal(self):
        """A drop > stop_loss_pct forces a SELL even without a normal sell signal."""
        # Row 1: BUY at 100; Row 2: HOLD at 80 (–20 % < –15 % threshold)
        df = _df([_buy_row(100.0), _hold_row(80.0)])
        result = run_backtest(df, cfg=BacktestConfig(stop_loss_pct=0.15, commission_pct=0.0, commission_min=0.0))
        assert result.stop_loss_exits == 1
        sell_row = result.trades[result.trades["side"] == "SELL"].iloc[0]
        assert sell_row["stop_loss"] == True  # noqa: E712 — numpy bool needs ==

    def test_no_stop_loss_when_price_recovers(self):
        """stop_loss_exits == 0 when price never drops enough below entry."""
        # BUY at 100, hold at 95 (–5 %), then normal SELL
        df = _df([_buy_row(100.0), _hold_row(95.0), _sell_row(90.0)])
        result = run_backtest(df, cfg=BacktestConfig(stop_loss_pct=0.15, commission_pct=0.0, commission_min=0.0))
        assert result.stop_loss_exits == 0

    def test_stop_loss_increments_counter(self):
        """stop_loss_exits counts only stop-loss-triggered SELLs, not normal SELLs."""
        df = _df([_buy_row(100.0), _sell_row(90.0)])  # normal sell, no stop-loss
        result = run_backtest(df, cfg=BacktestConfig(stop_loss_pct=0.15, commission_pct=0.0, commission_min=0.0))
        assert result.stop_loss_exits == 0
