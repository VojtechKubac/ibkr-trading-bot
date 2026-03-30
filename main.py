from __future__ import annotations

import argparse
import json
import logging
import math
from dataclasses import asdict
from datetime import date
from pathlib import Path

from trading_bot.data import fetch_ohlcv
from trading_bot.logging_config import setup_logging
from trading_bot.signals import IndicatorConfig, enrich_with_indicators, latest_signal
from trading_bot.broker_ibkr import DryRunSkipped, IBKRConfig, OrderSkipped, execute_signal_as_market_order
from trading_bot.assets import get_asset
from trading_bot.backtest import BacktestConfig, run_backtest
from trading_bot.metrics import build_performance_report
from trading_bot import config


def parse_args() -> argparse.Namespace:
    """Parse and return CLI arguments for the signal-check / backtest entry point."""
    parser = argparse.ArgumentParser(
        description="Run a single Phase 1 weekly trend/momentum signal check.",
    )
    parser.add_argument(
        "--symbol",
        default="VWCE.DE",
        help="Ticker symbol to analyse (default: VWCE.DE).",
    )
    parser.add_argument(
        "--asset",
        default=None,
        help="Optional asset key (e.g. 'vwce', 'spy'); if provided, overrides --symbol and --ibkr-symbol.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=365 * 5,
        help="Number of calendar days of history to fetch (default: 1825).",
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="If set, run a simple backtest over the full history instead of only showing the latest signal.",
    )
    parser.add_argument(
        "--backtest-initial-cash",
        type=float,
        default=10_000.0,
        help="Initial cash for backtest (default: 10000).",
    )
    parser.add_argument(
        "--backtest-position-size",
        type=int,
        default=1,
        help="Fixed number of shares to trade on BUY signals during backtest (default: 1).",
    )
    parser.add_argument(
        "--backtest-sizing-mode",
        choices=["fixed", "percent_equity"],
        default="fixed",
        help="Backtest sizing mode: fixed shares or percent-of-equity.",
    )
    parser.add_argument(
        "--backtest-percent-equity",
        type=float,
        default=1.0,
        help="When --backtest-sizing-mode=percent_equity, fraction of equity to allocate (0..1).",
    )
    parser.add_argument(
        "--backtest-min-position-size",
        type=int,
        default=1,
        help="Minimum share size to allow a BUY in percent_equity sizing (default: 1).",
    )
    parser.add_argument(
        "--backtest-commission-pct",
        type=float,
        default=0.001,
        help="Commission as fraction of trade value, e.g. 0.001 = 0.1%% (default: 0.001).",
    )
    parser.add_argument(
        "--backtest-stop-loss-pct",
        type=float,
        default=0.15,
        help="Stop-loss threshold as fraction below entry price, e.g. 0.15 = 15%% (default: 0.15).",
    )
    parser.add_argument(
        "--backtest-report-json",
        default=None,
        help="Optional path to write a JSON performance report for the backtest.",
    )
    parser.add_argument(
        "--ibkr-enable",
        action="store_true",
        help="If set, attempt to execute the signal via IBKR (use paper account first!).",
    )
    parser.add_argument(
        "--ibkr-symbol",
        default="VWCE",
        help="IBKR symbol to trade (default: VWCE, note: differs from Yahoo's VWCE.DE).",
    )
    parser.add_argument(
        "--ibkr-host",
        default=config.IBKR_HOST,
        help=f"Host where TWS / IB Gateway is running (default: {config.IBKR_HOST}).",
    )
    parser.add_argument(
        "--ibkr-port",
        type=int,
        default=config.IBKR_PORT,
        help=f"Port for TWS / IB Gateway (default: {config.IBKR_PORT}).",
    )
    parser.add_argument(
        "--ibkr-client-id",
        type=int,
        default=config.IBKR_CLIENT_ID,
        help=f"Client ID for the IBKR API connection (default: {config.IBKR_CLIENT_ID}).",
    )
    parser.add_argument(
        "--ibkr-account",
        default=config.IBKR_ACCOUNT,
        help="Optional IBKR account ID; if omitted, IBKR will use the default account.",
    )
    parser.add_argument(
        "--ibkr-size",
        type=int,
        default=1,
        help="Number of shares to trade when executing a BUY/SELL signal (default: 1).",
    )
    return parser.parse_args()


def main() -> None:
    """Run a signal check or backtest, and optionally execute via IBKR."""
    setup_logging()
    args = parse_args()

    if args.asset:
        asset = get_asset(args.asset)
        yahoo_symbol = asset.yahoo_symbol
        ib_symbol = asset.ib_symbol
    else:
        yahoo_symbol = args.symbol
        ib_symbol = args.ibkr_symbol

    print("=== Trading Bot Phase 1 — Data + Signal ===")
    print(f"Date: {date.today().isoformat()}")
    print(f"Asset: {args.asset or yahoo_symbol}")
    print()

    df = fetch_ohlcv(
        symbol=yahoo_symbol,
        lookback_days=args.lookback_days,
    )

    df_ind = enrich_with_indicators(df, IndicatorConfig())

    if args.backtest:
        print("=== Backtest ===")
        bt_cfg = BacktestConfig(
            initial_cash=args.backtest_initial_cash,
            sizing_mode=args.backtest_sizing_mode,
            position_size=args.backtest_position_size,
            percent_equity=args.backtest_percent_equity,
            min_position_size=args.backtest_min_position_size,
            commission_pct=args.backtest_commission_pct,
            stop_loss_pct=args.backtest_stop_loss_pct,
        )
        result = run_backtest(df_ind, cfg=bt_cfg)
        print(f"Initial equity:   {bt_cfg.initial_cash:.2f}")
        print(f"Sizing mode:      {bt_cfg.sizing_mode}")
        print(f"Final equity:     {result.equity_curve.iloc[-1]:.2f}")
        print(f"Total return:     {result.total_return * 100:.2f}%")
        print(f"Benchmark return: {result.benchmark_return * 100:.2f}%  (buy-and-hold)")
        print(f"Max drawdown:     {result.max_drawdown * 100:.2f}%")
        print(f"Commission paid:  {result.commission_paid:.2f}")
        print(f"Stop-loss exits:  {result.stop_loss_exits}")
        print()
        print(f"Number of trades: {len(result.trades)}")
        report = build_performance_report(
            equity_curve=result.equity_curve,
            trades=result.trades,
            position_curve=result.position_curve,
        )
        print("=== Performance report ===")
        if report.cagr is not None:
            print(f"CAGR:            {report.cagr * 100:.2f}%")
        if report.annualized_volatility is not None:
            print(f"Ann. volatility: {report.annualized_volatility * 100:.2f}%")
        if report.sharpe is not None:
            print(f"Sharpe (rf=0):   {report.sharpe:.2f}")
        if report.exposure is not None:
            print(f"Exposure:        {report.exposure * 100:.2f}%")
        if report.turnover is not None:
            print(f"Turnover:        {report.turnover:.4f}")
        if report.win_rate is not None:
            print(f"Win rate:        {report.win_rate * 100:.2f}%")
        if report.avg_win is not None:
            print(f"Avg win:         {report.avg_win:.2f}")
        if report.avg_loss is not None:
            print(f"Avg loss:        {report.avg_loss:.2f}")
        if report.expectancy is not None:
            print(f"Expectancy:      {report.expectancy:.2f}")
        print(f"Round trips:     {report.trade_round_trips}")
        print()
        if args.backtest_report_json:
            out_path = Path(args.backtest_report_json)
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(asdict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
            except OSError as exc:
                logging.getLogger(__name__).error("Failed to write backtest report: %s", exc)
                raise SystemExit(1) from exc
        if not result.trades.empty:
            print("First 5 trades:")
            print(result.trades.head())
        return

    ts, sig, row = latest_signal(df_ind)

    price = row['close']
    ma_short = row['ma_short']
    ma_long = row['ma_long']
    rsi = row['rsi']

    print(f"Latest bar: {ts}")
    print(f"Close price: {price:.2f}")
    print(f"50d MA: {ma_short:.2f} | 200d MA: {ma_long:.2f}")
    if not math.isnan(rsi):
        print(f"RSI(14): {rsi:.2f}")
    print()
    print(f"Phase 1 signal: {sig}")

    if args.ibkr_enable:
        print()
        print("=== IBKR Execution ===")
        cfg = IBKRConfig(
            host=args.ibkr_host,
            port=args.ibkr_port,
            client_id=args.ibkr_client_id,
            account=args.ibkr_account,
        )
        try:
            trade = execute_signal_as_market_order(
                sig,
                ib_symbol=ib_symbol,
                quantity=args.ibkr_size,
                reference_price=float(price),
                cfg=cfg,
            )
        except Exception as exc:  # pragma: no cover - runtime integration errors
            print(f"IBKR execution failed: {exc}")
        else:
            if trade is None:
                print("Signal was HOLD — no IBKR order sent.")
            elif isinstance(trade, DryRunSkipped):
                print(f"DRYRUN mode — {trade.signal} order for {trade.quantity} x {trade.ib_symbol} skipped.")
            elif isinstance(trade, OrderSkipped):
                print(f"Order skipped ({trade.reason}) — {trade.signal} for {trade.ib_symbol}.")
            else:
                print(f"IBKR order sent. Order ID: {trade.orderId}, status: {trade.orderStatus.status}")


if __name__ == "__main__":
    main()

