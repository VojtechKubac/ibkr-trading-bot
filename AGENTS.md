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
  config.py           Central config loaded from environment / .env
  logging_config.py   Structured logging setup
main.py               CLI entry point: signal check, backtest, optional IBKR execution
requirements.txt      Runtime dependencies
requirements-dev.txt  Dev-only tools: pytest, ruff, mypy
trading-bot-plan.md   High-level project and strategy plan
tests/                Unit tests
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
- **Config via `.env`** (see `.env.example`); never hardcode credentials or account IDs.
- **Logging**: each module uses `logging.getLogger(__name__)` — no `print()` in library code. `main.py` may print to stdout for human-readable CLI output.
- **Tests**: use `pytest`; no real network calls in unit tests — mock `yf.Ticker.history` for data tests and `IBKRClient` / `IB` for broker tests.
- **Docstrings**: all public methods and classes must have a docstring. Dunder methods (`__init__`, `__enter__`, `__exit__`) should have a one-line docstring when their behaviour is non-obvious.
- **IBKR network calls**: wrap `ib_insync` calls that can fail mid-connection (e.g. `ib.positions()`, `ib.placeOrder()`) in `try/except`; log the error with `exc_info=True` and return a safe fallback rather than letting a raw network exception propagate to the caller.
- **PR size target**: ~200 lines, hard limit 500 lines (tests included).

## Workflow

- One Linear ticket = one PR.
- One Linear ticket = one dedicated git worktree + one branch + one Docker container.
- **Always branch from `main`**, never from another feature branch.
- Branch naming: `kua-{number}-short-description` (e.g. `kua-19-agent-docs`).
- All CodeRabbit review comments must be resolved before requesting human review.
- **When working on an open PR, always check for merge conflicts first** (`git fetch origin main && git merge origin/main`). Resolve any conflicts before making further changes or pushing.
- Do not merge your own PRs.

### Ticket Environment Bootstrap

Use the helper script from the main repository checkout:

```bash
./scripts/new-ticket-env.sh kua-123 short-description
```

This creates a new worktree under `../worktrees/` from `origin/main` and writes a `.ticket-env` file with container/runtime variables.

Inside the new worktree, start the ticket container:

```bash
set -a; source .ticket-env; set +a
docker compose -f docker-compose.ticket.yml up -d --build
docker compose -f docker-compose.ticket.yml exec ticket-dev bash
```

### Running the AI agent inside the container

Both Claude Code and Cursor CLI are installed in the container. Only `ANTHROPIC_API_KEY` and `CURSOR_API_KEY` are forwarded from the host shell; IBKR credentials are intentionally not forwarded (see `docker-compose.ticket.yml`).

**Claude Code:**

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # in host shell, before docker compose up
# inside the container:
claude --dangerously-skip-permissions
```

**Cursor agent CLI:**

```bash
export CURSOR_API_KEY=...             # in host shell, before docker compose up
# inside the container:
cursor-agent -p --force --sandbox disabled "implement the ticket"
```

`-p` = non-interactive/headless, `--force` = apply changes without confirmation, `--sandbox disabled` = allow the agent to run shell commands freely (equivalent to Claude Code's `--dangerously-skip-permissions`).

The container has outbound internet access (needed for API calls and package downloads). The safety guarantee is **host filesystem isolation**, not network isolation:

- The agent can only read/write `/workspace` (the ticket worktree). The rest of the host filesystem is not mounted.
- `cap_drop: ALL` and `no-new-privileges` prevent privilege escalation, so the agent cannot break out of the container.
- Destructive commands like `rm -rf /` only affect the container's ephemeral filesystem, not the host.
- A fresh worktree contains no `.env` file (`.env` is gitignored and never committed). IBKR credentials are therefore not present in `/workspace` during normal agentic use.

### Editing with Cursor GUI

Cursor GUI does not run inside the container. Two options:

- **Direct**: Open the worktree directory (`../worktrees/kua-xxx-yyy/`) in Cursor on the host. The worktree is on the host filesystem, so Cursor sees all changes the container makes immediately.
- **Remote**: Use [Cursor Remote SSH](https://docs.cursor.com/remote/overview) to connect into the running container.

### Rules for agentic sessions

- Run coding agents from the ticket worktree only, never from another ticket directory.
- Keep container mounts limited to the ticket worktree.
- For parallel ticket work, create one worktree/container pair per ticket.
- Stop and remove ticket containers when work is complete.
- **Never place `.env` files with real IBKR credentials inside a ticket worktree.** A worktree created from `origin/main` will not contain one (`.env` is gitignored), and it must stay that way. Only `ANTHROPIC_API_KEY` and `CURSOR_API_KEY` are forwarded from the host shell into the container; IBKR credentials (`IBKR_*`) are intentionally not forwarded.
- Ticket containers enforce `DRYRUN=true` and `IBKR_ENABLE=false` unconditionally (set in `docker-compose.ticket.yml`). Live order placement from a ticket container is not possible even if credentials are present.

## What NOT to Do

- Never place real IBKR orders unless `--ibkr-enable` **and** `DRYRUN=false` are explicitly set.
- Never commit `.env` or `.db` files.
- Avoid modifying `scheduler/` files before reading `scheduler/README.md` (coming soon).
