from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from trading_bot.signals import Signal, rule_phase1_signal_for_row

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for a single-asset backtest run."""

    initial_cash: float = 10_000.0
    position_size: int = 1
    commission_pct: float = 0.001   # 0.1 % of trade value
    commission_min: float = 1.0     # minimum commission per trade (EUR/USD)
    stop_loss_pct: float = 0.15     # force SELL when price drops >15 % from entry


@dataclass
class BacktestResult:
    """Container for the results of a backtest run."""

    equity_curve: pd.Series
    trades: pd.DataFrame
    total_return: float
    max_drawdown: float
    commission_paid: float
    stop_loss_exits: int
    benchmark_return: float


def run_backtest(
    df_with_indicators: pd.DataFrame,
    *,
    cfg: BacktestConfig | None = None,
) -> BacktestResult:
    """
    Single-asset backtest with optional commission costs and stop-loss simulation.

    - Uses Phase 1 signal on each bar.
    - Enters/exits with a fixed share size configured via ``cfg.position_size``.
    - Commission is deducted on both BUY and SELL.
    - Stop-loss is checked on every bar; if triggered the SELL is marked in the
      trades DataFrame and counted in ``stop_loss_exits``.
    - Execution price uses ``adj_close`` when present, else ``close``.
    - At most one position open at a time (long or flat).

    Raises:
        ValueError: If ``df_with_indicators`` is empty.
    """
    if cfg is None:
        cfg = BacktestConfig()

    if df_with_indicators.empty:
        raise ValueError("df_with_indicators must contain at least one row")

    price_col = "adj_close" if "adj_close" in df_with_indicators.columns else "close"

    benchmark_return = (
        float(df_with_indicators[price_col].iloc[-1])
        / float(df_with_indicators[price_col].iloc[0])
    ) - 1.0

    cash = cfg.initial_cash
    position = 0        # number of shares held
    entry_price = 0.0   # price at which current position was opened
    equity: list[tuple] = []
    trades: list[dict] = []
    commission_paid = 0.0
    stop_loss_exits = 0

    for ts, row in df_with_indicators.iterrows():
        price = float(row[price_col])
        signal: Signal = rule_phase1_signal_for_row(row)

        # Stop-loss overrides the signal when the position is open.
        stop_loss_triggered = False
        if position > 0 and entry_price > 0:
            if (price - entry_price) / entry_price <= -cfg.stop_loss_pct:
                signal = "SELL"
                stop_loss_triggered = True

        if signal == "BUY" and position == 0:
            trade_value = cfg.position_size * price
            commission = max(trade_value * cfg.commission_pct, cfg.commission_min)
            total_cost = trade_value + commission
            if total_cost <= cash:
                cash -= total_cost
                position += cfg.position_size
                entry_price = price
                commission_paid += commission
                trades.append({
                    "timestamp": ts,
                    "side": "BUY",
                    "price": price,
                    "size": cfg.position_size,
                    "commission": commission,
                    "stop_loss": False,
                })

        elif signal == "SELL" and position > 0:
            proceeds = position * price
            commission = max(proceeds * cfg.commission_pct, cfg.commission_min)
            cash += proceeds - commission
            commission_paid += commission
            if stop_loss_triggered:
                stop_loss_exits += 1
            trades.append({
                "timestamp": ts,
                "side": "SELL",
                "price": price,
                "size": position,
                "commission": commission,
                "stop_loss": stop_loss_triggered,
            })
            position = 0
            entry_price = 0.0

        equity.append((ts, cash + position * price))

    equity_series = pd.Series(
        data=[v for _, v in equity],
        index=[t for t, _ in equity],
        name="equity",
    )

    total_return = (equity_series.iloc[-1] / cfg.initial_cash) - 1.0
    running_max = equity_series.cummax()
    max_drawdown = float(((equity_series / running_max) - 1.0).min())
    trades_df = pd.DataFrame(trades)

    logger.debug(
        "Backtest complete: %d trades, return=%.2f%%, drawdown=%.2f%%, "
        "commission=%.2f, stop_loss_exits=%d, benchmark=%.2f%%",
        len(trades),
        float(total_return) * 100,
        max_drawdown * 100,
        commission_paid,
        stop_loss_exits,
        benchmark_return * 100,
    )
    return BacktestResult(
        equity_curve=equity_series,
        trades=trades_df,
        total_return=float(total_return),
        max_drawdown=max_drawdown,
        commission_paid=commission_paid,
        stop_loss_exits=stop_loss_exits,
        benchmark_return=benchmark_return,
    )


def run_backtest_fixed_size(
    df_with_indicators: pd.DataFrame,
    *,
    initial_cash: float = 10_000.0,
    position_size: int = 1,
) -> BacktestResult:
    """Backward-compatible alias for :func:`run_backtest` using default commission/stop-loss config."""
    return run_backtest(
        df_with_indicators,
        cfg=BacktestConfig(initial_cash=initial_cash, position_size=position_size),
    )
