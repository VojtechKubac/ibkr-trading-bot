"""Tests for --strategy CLI flag and strategy routing in run_backtest."""
from __future__ import annotations

import argparse

import pandas as pd
import pytest

from trading_bot.backtest import run_backtest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal enriched DataFrame for backtest."""
    idx = pd.date_range("2020-01-01", periods=len(rows), freq="D")
    return pd.DataFrame(rows, index=idx)


def _buy_row(close: float) -> dict:
    """Row that triggers BUY under the simple strategy."""
    return {"close": close, "ma_short": close * 0.9, "ma_long": close * 0.8, "rsi": 55.0}


def _sell_row(close: float) -> dict:
    """Row that triggers SELL under the simple strategy."""
    return {"close": close, "ma_short": close * 1.1, "ma_long": close * 1.2, "rsi": 45.0}


def _hold_row(close: float) -> dict:
    """Row that triggers HOLD: NaN MAs."""
    return {"close": close, "ma_short": float("nan"), "ma_long": float("nan"), "rsi": 50.0}


# ---------------------------------------------------------------------------
# run_backtest signal_fn parameter
# ---------------------------------------------------------------------------

class TestRunBacktestSignalFn:
    """Verify run_backtest routes signals through the supplied signal_fn."""

    def test_always_hold_fn_produces_no_trades(self):
        """A signal_fn that always returns HOLD should yield no trades."""
        df = _df([_buy_row(100.0), _buy_row(110.0), _buy_row(120.0)])

        result = run_backtest(df, signal_fn=lambda row: "HOLD")

        assert result.trades.empty
        assert result.total_return == pytest.approx(0.0)

    def test_always_buy_fn_opens_position_on_first_bar(self):
        """A signal_fn that always returns BUY should place a BUY on bar 2 (next-bar execution)."""
        df = _df([_hold_row(100.0), _hold_row(100.0), _hold_row(100.0)])

        result = run_backtest(df, signal_fn=lambda row: "BUY")

        # BUY is executed on bar 2 (next-bar), position stays open → 1 BUY trade.
        buy_trades = result.trades[result.trades["side"] == "BUY"]
        assert len(buy_trades) == 1

    def test_custom_fn_overrides_default_simple_rules(self):
        """signal_fn overrides the default Phase 1 rules."""
        # Rows that would trigger BUY under simple rules, but fn always returns HOLD.
        df = _df([_buy_row(100.0), _buy_row(110.0), _buy_row(120.0)])

        result_simple = run_backtest(df)           # default: simple rules → BUY triggered
        result_hold = run_backtest(df, signal_fn=lambda row: "HOLD")

        assert len(result_simple.trades) > 0
        assert result_hold.trades.empty

    def test_default_signal_fn_equals_simple_strategy(self):
        """run_backtest() with no signal_fn should produce identical results to the simple strategy."""
        from trading_bot.signals import rule_phase1_signal_for_row

        df = _df([_buy_row(50.0), _sell_row(100.0), _hold_row(100.0)])

        result_default = run_backtest(df)
        result_explicit = run_backtest(df, signal_fn=rule_phase1_signal_for_row)

        assert result_default.total_return == pytest.approx(result_explicit.total_return)
        assert len(result_default.trades) == len(result_explicit.trades)

    def test_weighted_strategy_uses_different_signal_fn(self):
        """weighted_signal_for_row can be passed as signal_fn without error."""
        from trading_bot.scoring import weighted_signal_for_row

        # Include all columns needed by weighted scoring.
        rows = [
            {
                "close": 110.0, "ma_short": 100.0, "ma_long": 90.0, "rsi": 65.0,
                "macd_hist": 1.0, "bb_upper": 120.0, "bb_lower": 95.0,
            },
            {
                "close": 108.0, "ma_short": 101.0, "ma_long": 91.0, "rsi": 60.0,
                "macd_hist": 0.5, "bb_upper": 121.0, "bb_lower": 96.0,
            },
            {
                "close": 105.0, "ma_short": 102.0, "ma_long": 92.0, "rsi": 55.0,
                "macd_hist": 0.2, "bb_upper": 122.0, "bb_lower": 97.0,
            },
        ]
        df = _df(rows)

        result = run_backtest(df, signal_fn=weighted_signal_for_row)

        assert result.equity_curve is not None
        assert len(result.equity_curve) == len(df)


# ---------------------------------------------------------------------------
# CLI --strategy flag
# ---------------------------------------------------------------------------

class TestStrategyCliFlag:
    """Verify parse_args handles --strategy correctly."""

    def _parse(self, *extra: str) -> argparse.Namespace:
        """Call parse_args with --backtest and optional extra args."""
        import sys
        from unittest.mock import patch

        with patch.object(sys, "argv", ["main.py", "--backtest"] + list(extra)):
            from main import parse_args
            return parse_args()

    def test_default_strategy_is_both(self):
        args = self._parse()
        assert args.strategy == "both"

    def test_strategy_simple(self):
        args = self._parse("--strategy", "simple")
        assert args.strategy == "simple"

    def test_strategy_weighted(self):
        args = self._parse("--strategy", "weighted")
        assert args.strategy == "weighted"

    def test_strategy_both_explicit(self):
        args = self._parse("--strategy", "both")
        assert args.strategy == "both"

    def test_invalid_strategy_raises(self):
        import sys
        from unittest.mock import patch

        with patch.object(sys, "argv", ["main.py", "--backtest", "--strategy", "invalid"]):
            from main import parse_args
            with pytest.raises(SystemExit):
                parse_args()
