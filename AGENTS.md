# AGENTS.md — Trading Bot (Primary Source of Truth)

This file is the authoritative guide for all coding agents working in this repository.

## Project Overview

This is a weekly trend/momentum trading bot that generates BUY/HOLD/SELL signals for a single ETF (default: VWCE.DE) using 50-day MA, 200-day MA, and 14-day RSI indicators. It runs on a weekly cadence, supports both IBKR paper and live trading via `ib_insync`, and is deliberately kept simple: no ORM, no complex frameworks. The project is in Phase 1 (data + signals); scheduling, monitoring, and multi-asset support are planned for later phases.

## Repository Structure

```text
trading_bot/          Core package
  __init__.py         Package marker
  data.py             OHLCV price data fetching via yfinance
  signals.py          Indicator computation (MA, RSI) and Phase 1 signal rules
  broker_ibkr.py      Thin IBKR order execution wrapper via ib_insync
  assets.py           Shared asset universe mapping Yahoo Finance to IBKR symbols
  backtest.py         Fixed-size single-asset backtester using Phase 1 rules
main.py               CLI entry point: signal check, backtest, optional IBKR execution
requirements.txt      Runtime dependencies
requirements-dev.txt  Dev-only tools: pytest, ruff, mypy
trading-bot-plan.md   High-level project and strategy plan
tests/                Unit tests (coming soon)
scheduler/            Scheduling infrastructure (coming soon)
runweekly.py          Weekly cron entry point (coming soon)
```

## Development Commands

```bash
# Install runtime + dev dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run tests
pytest tests/

# Run linter
ruff check .

# Run type checker
mypy trading_bot/ main.py

# Run signal check (dry — no orders placed)
python main.py --asset vwce

# Run backtest
python main.py --asset vwce --backtest

# Run weekly (dry)
DRYRUN=true python runweekly.py                      # coming soon
```

## Conventions

- **Python 3.12**; no ORM, no complex frameworks.
- **Config via `.env`** (see `.env.example` — coming soon); never hardcode credentials or account IDs.
- **Logging**: each module uses `logging.getLogger(__name__)` — no `print()` in library code. `main.py` may print to stdout for human-readable CLI output.
- **Tests**: use `pytest`; no real network calls in unit tests — mock `yf.Ticker.history` for data tests.
- **PR size target**: ~200 lines, hard limit 500 lines (tests included).

## Workflow

- One Linear ticket = one PR.
- **Always branch from `main`**, never from another feature branch.
- Branch naming: `kua-{number}-short-description` (e.g. `kua-19-agent-docs`).
- All CodeRabbit review comments must be resolved before requesting human review.
- **When working on an open PR, always check for merge conflicts first** (`git fetch origin main && git merge origin/main`). Resolve any conflicts before making further changes or pushing.
- Do not merge your own PRs.

## What NOT to Do

- Never place real IBKR orders unless `--ibkr-enable` **and** `DRYRUN=false` are explicitly set.
- Never commit `.env` or `.db` files.
- Avoid modifying `scheduler/` files before reading `scheduler/README.md` (coming soon).
