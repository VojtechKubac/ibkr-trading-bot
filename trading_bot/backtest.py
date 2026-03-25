from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from trading_bot.signals import Signal, rule_phase1_signal_for_row

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Container for the results of a fixed-size backtest run."""

    equity_curve: pd.Series
    trades: pd.DataFrame
    total_return: float
    max_drawdown: float


def run_backtest_fixed_size(
    df_with_indicators: pd.DataFrame,
    *,
    initial_cash: float = 10_000.0,
    position_size: int = 1,
) -> BacktestResult:
    """
    Very simple single-asset backtest:

    - Uses Phase 1 signal on each bar.
    - Enters/exits with fixed share size on BUY/SELL.
    - No fees, slippage, or partial fills.
    - At most one position (long or flat).
    """
    cash = initial_cash
    position = 0  # number of shares
    equity = []
    trades = []

    for ts, row in df_with_indicators.iterrows():
        price = float(row["close"])
        signal: Signal = rule_phase1_signal_for_row(row)

        # Execute trading rule
        if signal == "BUY" and position == 0:
            # Buy fixed number of shares if we have enough cash.
            cost = position_size * price
            if cost <= cash:
                cash -= cost
                position += position_size
                trades.append(
                    {"timestamp": ts, "side": "BUY", "price": price, "size": position_size}
                )
        elif signal == "SELL" and position > 0:
            proceeds = position * price
            cash += proceeds
            trades.append(
                {"timestamp": ts, "side": "SELL", "price": price, "size": position}
            )
            position = 0

        equity_value = cash + position * price
        equity.append((ts, equity_value))

    equity_series = pd.Series(
        data=[v for _, v in equity],
        index=[ts for ts, _ in equity],
        name="equity",
    )

    total_return = (equity_series.iloc[-1] / initial_cash) - 1.0

    running_max = equity_series.cummax()
    drawdown = (equity_series / running_max) - 1.0
    max_drawdown = float(drawdown.min())

    trades_df = pd.DataFrame(trades)

    logger.debug(
        "Backtest complete: %d trades, total_return=%.2f%%, max_drawdown=%.2f%%",
        len(trades),
        float(total_return) * 100,
        max_drawdown * 100,
    )
    return BacktestResult(
        equity_curve=equity_series,
        trades=trades_df,
        total_return=float(total_return),
        max_drawdown=max_drawdown,
    )

