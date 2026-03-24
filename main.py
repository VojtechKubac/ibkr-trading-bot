from __future__ import annotations

import argparse
from datetime import date

from trading_bot.data import fetch_ohlcv
from trading_bot.signals import IndicatorConfig, enrich_with_indicators, latest_signal
from trading_bot.broker_ibkr import IBKRConfig, execute_signal_as_market_order
from trading_bot.assets import get_asset
from trading_bot.backtest import run_backtest_fixed_size


def parse_args() -> argparse.Namespace:
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
        default="127.0.0.1",
        help="Host where TWS / IB Gateway is running (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--ibkr-port",
        type=int,
        default=7497,
        help="Port for TWS / IB Gateway (default: 7497 for paper trading).",
    )
    parser.add_argument(
        "--ibkr-client-id",
        type=int,
        default=1,
        help="Client ID for the IBKR API connection (default: 1).",
    )
    parser.add_argument(
        "--ibkr-account",
        default=None,
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
        print("=== Backtest (fixed-size position) ===")
        result = run_backtest_fixed_size(
            df_ind,
            initial_cash=args.backtest_initial_cash,
            position_size=args.backtest_position_size,
        )
        print(f"Initial equity: {args.backtest_initial_cash:.2f}")
        print(f"Final equity:   {result.equity_curve.iloc[-1]:.2f}")
        print(f"Total return:   {result.total_return * 100:.2f}%")
        print(f"Max drawdown:   {result.max_drawdown * 100:.2f}%")
        print()
        print(f"Number of trades: {len(result.trades)}")
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
    if not (rsi != rsi):  # simple NaN check
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
                cfg=cfg,
            )
        except Exception as exc:  # pragma: no cover - runtime integration errors
            print(f"IBKR execution failed: {exc}")
        else:
            if trade is None:
                print("Signal was HOLD — no IBKR order sent.")
            else:
                print(f"IBKR order sent. Order ID: {trade.orderId}, status: {trade.orderStatus.status}")


if __name__ == "__main__":
    main()

