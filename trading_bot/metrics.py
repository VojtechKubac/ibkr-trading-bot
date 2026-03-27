from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PerformanceReport:
    """Performance metrics derived from a backtest run."""

    cagr: float | None
    annualized_volatility: float | None
    sharpe: float | None
    win_rate: float | None
    avg_win: float | None
    avg_loss: float | None
    expectancy: float | None
    turnover: float | None
    exposure: float | None
    trade_round_trips: int


def _years_between(index: pd.Index) -> float | None:
    if len(index) < 2:
        return None
    if not isinstance(index, pd.DatetimeIndex):
        return None
    dt = index[-1] - index[0]
    days = dt.total_seconds() / (24 * 3600)
    if days <= 0:
        return None
    return days / 365.25


def _periods_per_year(index: pd.Index) -> float | None:
    """Best-effort estimate of periods/year from a DatetimeIndex."""

    if not isinstance(index, pd.DatetimeIndex) or len(index) < 3:
        return None

    try:
        freq = pd.infer_freq(index)
    except Exception:
        freq = None

    if freq:
        f = freq.upper()
        if f.startswith("B"):
            return 252.0
        if f.startswith("D"):
            return 252.0
        if f.startswith("W"):
            return 52.0
        if f.startswith("M"):
            return 12.0
        if f.startswith("Q"):
            return 4.0
        if f.startswith("A") or f.startswith("Y"):
            return 1.0

    deltas = index.to_series().diff().dropna()
    if deltas.empty:
        return None
    median_days = deltas.dt.total_seconds().median() / (24 * 3600)
    if not median_days or median_days <= 0:
        return None
    return 365.25 / float(median_days)


def _round_trip_pnls(trades: pd.DataFrame) -> list[float]:
    if trades.empty:
        return []

    # Expect BUY/SELL alternating, but be defensive.
    pnls: list[float] = []
    open_buy: dict | None = None

    for row in trades.to_dict(orient="records"):
        side = row.get("side")
        if side == "BUY":
            open_buy = row
            continue
        if side == "SELL" and open_buy is not None:
            size = float(open_buy.get("size", 0) or 0)
            buy_price = float(open_buy.get("price", 0) or 0)
            sell_price = float(row.get("price", 0) or 0)
            buy_comm = float(open_buy.get("commission", 0) or 0)
            sell_comm = float(row.get("commission", 0) or 0)

            buy_cost = size * buy_price + buy_comm
            sell_proceeds = size * sell_price - sell_comm
            pnls.append(sell_proceeds - buy_cost)
            open_buy = None

    return pnls


def build_performance_report(
    *,
    equity_curve: pd.Series,
    trades: pd.DataFrame,
    position_curve: pd.Series | None = None,
) -> PerformanceReport:
    """Compute a standardized performance report from backtest outputs."""

    equity_curve = equity_curve.dropna()
    if equity_curve.empty:
        return PerformanceReport(
            cagr=None,
            annualized_volatility=None,
            sharpe=None,
            win_rate=None,
            avg_win=None,
            avg_loss=None,
            expectancy=None,
            turnover=None,
            exposure=None,
            trade_round_trips=0,
        )

    years = _years_between(equity_curve.index)
    cagr: float | None
    if years and years > 0 and float(equity_curve.iloc[0]) > 0:
        cagr = float((float(equity_curve.iloc[-1]) / float(equity_curve.iloc[0])) ** (1.0 / years) - 1.0)
    else:
        cagr = None

    rets = equity_curve.pct_change().dropna()
    ppy = _periods_per_year(equity_curve.index)
    ann_vol: float | None = None
    sharpe: float | None = None

    if not rets.empty and ppy and ppy > 0:
        vol = float(rets.std(ddof=1))
        mean = float(rets.mean())
        if vol > 0:
            ann_vol = vol * math.sqrt(ppy)
            sharpe = (mean / vol) * math.sqrt(ppy)
        else:
            ann_vol = 0.0
            sharpe = None

    pnls = _round_trip_pnls(trades)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    trade_round_trips = len(pnls)
    win_rate = (len(wins) / trade_round_trips) if trade_round_trips else None
    avg_win = (sum(wins) / len(wins)) if wins else None
    avg_loss = (sum(losses) / len(losses)) if losses else None

    if win_rate is None:
        expectancy = None
    else:
        avg_win_val = avg_win or 0.0
        avg_loss_val = avg_loss or 0.0
        expectancy = win_rate * avg_win_val + (1.0 - win_rate) * avg_loss_val

    turnover: float | None = None
    if not trades.empty and "size" in trades.columns and "price" in trades.columns:
        traded_value = float((trades["size"] * trades["price"]).abs().sum())
        avg_equity = float(equity_curve.mean())
        if avg_equity > 0:
            turnover = traded_value / avg_equity

    exposure: float | None = None
    if position_curve is not None and not position_curve.empty:
        exposure = float((position_curve > 0).mean())

    return PerformanceReport(
        cagr=cagr,
        annualized_volatility=ann_vol,
        sharpe=sharpe,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        expectancy=expectancy,
        turnover=turnover,
        exposure=exposure,
        trade_round_trips=trade_round_trips,
    )
