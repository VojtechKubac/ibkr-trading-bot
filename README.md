## Trading Bot (Weekly Trend / Momentum)

This project implements a simple, **weekly trend/momentum trading agent** based on the plan in `trading-bot-plan.md`.

### Current Scope (Phase 1 — Data + Signals)

- Fetch daily OHLCV price data for a configured ETF (default: `VWCE.DE`) from Yahoo Finance.
- Default history window is ~5 years (where available) to support basic backtesting.
- Compute:
  - 50‑day moving average
  - 200‑day moving average
  - 14‑day RSI
- Generate a **weekly signal** for the most recent trading day using the Phase 1 rules:
  - BUY / HOLD / SELL

### Project Structure

- `trading_bot/`
  - `data.py` — price/volume data download utilities.
  - `signals.py` — indicator and trading signal calculations.
  - `broker_ibkr.py` — thin wrapper around Interactive Brokers via `ib_insync`.
  - `assets.py` — shared universe of tradable assets (Yahoo + IBKR symbols).
- `backtest.py` — simple single‑asset backtester using the Phase 1 rules.
- `main.py` — CLI entry point to run a one‑off signal check.
- `trading-bot-plan.md` — high‑level project and strategy plan.

### Quickstart

1. **Create a virtual environment** (recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # on Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Run a signal check** (default `VWCE.DE`):

   ```bash
   python main.py
   ```

   Or specify a symbol:

   ```bash
   python main.py --symbol SPY
   ```

   Or pick a preconfigured asset (uses both Yahoo and IBKR symbols):

   ```bash
   python main.py --asset vwce
   python main.py --asset spy
   ```

5. **Run a simple backtest (history only, no broker)**:

   ```bash
   python main.py --asset vwce --backtest
   ```

   Useful flags:

   - `--backtest-initial-cash`: starting equity (default: 10000).
   - `--backtest-position-size`: fixed number of shares to trade on BUY (default: 1).
   - Backtest timing uses **next-bar execution**: signals are evaluated on bar `t`, and orders fill on bar `t+1` to avoid same-bar bias.
   - A signal on the final bar is not filled because there is no subsequent bar, which can affect trade count and terminal PnL.

4. **(Optional) Execute via IBKR — use paper trading first!**

   With TWS or IB Gateway running locally:

   ```bash
   python main.py --ibkr-enable --ibkr-size 1
   ```

   Useful flags:

   - `--ibkr-symbol`: IBKR symbol to trade (default: `VWCE`, note Yahoo uses `VWCE.DE`).
   - `--ibkr-host`: Host where TWS / Gateway is running (default: `127.0.0.1`).
   - `--ibkr-port`: API port (default: `7497` for paper trading).
   - `--ibkr-client-id`: Client ID (default: `1`).
   - `--ibkr-account`: Optional account ID; if omitted, IBKR uses the default.

### Notes

- This is **Phase 1 only**: data + signal computation and a single‑run CLI.
- Paper trading, broker integration (IBKR), scheduling, and monitoring will be added in later phases.

### Isolated Ticket Workflow (Agentic)

For AI-assisted parallel development, use one isolated environment per ticket:

- one Linear ticket → one git branch/worktree → one Docker container

Create a new ticket environment from the main repository checkout:

```bash
./scripts/new-ticket-env.sh kua-123 short-description
```

Enter the worktree, start the container, and launch the agent in allow-all mode:

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # or CURSOR_API_KEY for Cursor agent
cd ../worktrees/kua-123-short-description
set -a; source .ticket-env; set +a
docker compose -f docker-compose.ticket.yml up -d --build
docker compose -f docker-compose.ticket.yml exec ticket-dev bash
# inside the container — pick one:
claude --dangerously-skip-permissions
cursor-agent -p --force --sandbox disabled "implement the ticket"
```

**What is and isn't isolated:** the container has outbound internet access (needed for API calls). The safety guarantee is host filesystem isolation — only `/workspace` (the ticket worktree) is mounted, `cap_drop: ALL` prevents privilege escalation, so the agent cannot touch the rest of your machine.

To run multiple tickets in parallel, repeat with a different ticket ID; each gets its own worktree and container.

To edit with Cursor GUI, open the worktree directory directly in Cursor on the host — it sees all changes immediately since the worktree lives on the host filesystem.

### Deployment Readiness

- For IBKR paper rollout go/no-go checks, follow `docs/ibkr-paper-go-no-go-checklist.md`.

