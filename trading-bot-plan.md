# Trading Bot — Preliminary Plan

A planning document for a personal trading agent project. Goals: learn from building a working system, and build long-term wealth. Constraints: ~4 hours/week, €500 starting capital + €100/month, EU (Czech Republic).

---

## 1. Project Context

| Factor | Value | Implication |
|--------|-------|-------------|
| **Time** | ~4 hours/week | Low-frequency strategies only; no day trading |
| **Capital** | €500 start, +€100/month | Small size; fees matter; limited diversification |
| **Location** | Czech Republic (EU) | MiFID II, ESMA rules, Czech tax treatment |
| **Risk tolerance** | Playground, but &lt;50% loss | Design for ~20–30% max drawdown |
| **Brokers** | Degiro, IBKR | IBKR preferred for automation |

---

## 2. Strategy Choice

### Selected: Weekly Trend / Momentum

- **Cadence:** Run once per week (e.g. Monday).
- **Logic:** For each asset, evaluate trend (e.g. price vs moving averages) and decide BUY, SELL, or HOLD.
- **Orders:** 0–N per week (one per asset that needs a change).

### Comparison to Alternatives

| Alternative | Why Not Chosen |
|-------------|----------------|
| **Day trading** | Requires constant monitoring; incompatible with 4 hrs/week |
| **Grid trading** | Works in sideways markets; strong trends can cause large drawdowns |
| **Passive DCA only** | No trading logic; limited learning value |
| **Crypto bots** | Higher volatility, EU regulatory uncertainty, more tax complexity |
| **Copy trading** | No agent-building; less control and learning |
| **High-frequency / HFT** | Requires infrastructure and capital; not realistic |

### Why Weekly Trend Fits

- Fully automatable (scheduled job).
- Few trades → low fee impact.
- Clear learning path: data → signals → rules → execution.
- Risk controllable via position sizing and stops.

---

## 3. Broker Choice

### Selected: Interactive Brokers (IBKR)

- Strong API (TWS API or Client Portal API).
- Low fees suitable for small capital.
- EU-regulated.

### Comparison to Alternatives

| Alternative | Why Not Chosen |
|-------------|----------------|
| **Degiro** | No official retail trading API; automation would require scraping or manual CSV |
| **Trading 212** | Limited API for automated trading |
| **Crypto-only exchanges** | Different asset class; can add later if desired |
| **Other EU brokers** | IBKR already available; good API support |

### Note

Degiro can remain for manual/long-term investing; the agent runs on IBKR.

---

## 4. Asset Choice

### Selected: Liquid Broad-Market ETF(s)

- **Examples:** VWCE (Vanguard FTSE All-World), SPY/SPYL or equivalent S&P 500 ETF.
- **Start:** One ETF to keep complexity low.

### Comparison to Alternatives

| Alternative | Why Not Chosen (for initial phase) |
|-------------|-----------------------------------|
| **Individual stocks** | More research; higher idiosyncratic risk; more complex fundamentals |
| **Crypto** | Higher volatility; different regulation and tax treatment |
| **Forex** | 24/7 markets; leverage; more complex for a first agent |
| **Multiple assets from day one** | €500 split across many = tiny positions; hard to learn from |
| **Options** | Extra complexity; ESMA restrictions on retail |

### Why ETF First

- Simple, liquid, low maintenance.
- One instrument = focus on agent logic.
- Easy to add more assets later.

---

## 5. Decision-Making Approach

### Selected: Simple Rules → Weighted Scoring (Phased)

**Phase 1:** Hard if/else rules (e.g. price vs MA, RSI).

**Phase 2:** Weighted scoring (combine several indicators with weights).

**Phase 3 (optional):** Decision tree or simple ML classifier for experimentation.

### Comparison to Alternatives

| Alternative | Why Not Chosen (for now) |
|-------------|--------------------------|
| **Reinforcement Learning** | Complex; data-hungry; unstable; overkill for 4 hrs/week |
| **LLM / large agent** | Unreliable; expensive; hard to backtest |
| **Pure ML from start** | Needs labels; overfitting risk; less interpretable |
| **Complex rule sets** | Hard to debug; diminishing returns early on |

### Why Start Simple

- Interpretable and debuggable.
- Fast to implement and iterate.
- Foundation for more advanced logic later.

---

## 6. Data Sources

### Selected (Phased)

| Phase | Data | Purpose |
|-------|------|---------|
| **Start** | Price/volume (OHLCV) | Core signals: MAs, RSI, trend |
| **Phase 2** | Calendar/events | Avoid trading around earnings, FOMC |
| **Phase 3** | Macro (1–2 indicators) | Regime filter (e.g. ECB rate, recession proxy) |
| **Phase 4** | Fundamentals | If moving to single stocks |
| **Later** | VIX, sentiment | Optional experiments |

### Comparison to Alternatives

| Alternative | Why Not Chosen (for now) |
|-------------|--------------------------|
| **News/sentiment from day one** | Free tiers limited; noisy; needs tuning |
| **Options flow** | Adds complexity; more relevant for options trading |
| **Satellite, web traffic, etc.** | Expensive; not realistic for budget |
| **Many macro indicators** | Maintenance burden; risk of overfitting |

### Data Source Summary

| Source | Cost | Effort | Signal Quality | Fit |
|--------|------|--------|----------------|-----|
| Price/volume | Free | Low | High | ✅ Core |
| Calendar/events | Free | Low | Medium | ✅ Phase 2 |
| Macro | Free | Low | Medium | ✅ Phase 3 |
| Fundamentals | Free tiers | Low | Medium–high | ✅ Phase 4 |
| VIX | Free | Medium | Medium | ⚠️ Optional |
| News/sentiment | Limited free | Medium–high | Low–medium | ⚠️ Optional |
| Alternative data | Expensive | High | Variable | ❌ Skip |

---

## 7. Risk Management

### Design Targets

- **Max drawdown:** ~20–30% (avoid 50%+).
- **Position sizing:** Single position ≤ 10–15% of portfolio.
- **Stop-loss:** Hard or trailing stop (e.g. exit if drawdown from entry &gt; 15%).

### Approach

- Build risk limits into the agent from the start.
- Validate in paper trading before going live.
- Start live with small size; scale up as confidence grows.

---

## 8. Implementation Phases

| Phase | Focus | Outcome |
|-------|-------|---------|
| **1. Data + signal** | Fetch prices; compute MAs, RSI | Clear signal per symbol/date |
| **2. Rules engine** | Map signal → BUY/SELL/HOLD + size | Concrete order logic |
| **3. Paper trading** | Simulate orders; log trades | Paper portfolio + PnL |
| **4. Broker integration** | Connect to IBKR API | Real orders (when enabled) |
| **5. Scheduling + monitoring** | Weekly cron; alerts/dashboard | Runs with minimal maintenance |

---

## 9. Example Rule Set (Phase 1)

```
Weekly check (per asset):
1. Fetch: price, 200-day MA, 50-day MA
2. Rules:
   - If price > 200_MA and price > 50_MA  → BUY (or HOLD if already long)
   - If price < 200_MA                   → SELL (or HOLD if already flat)
   - If price > 200_MA but price < 50_MA  → HOLD (potential reversal)
3. Position sizing: max 100% in single asset; optionally scale by volatility
4. Stop: if drawdown from entry > 15%, SELL regardless of signal
```

---

## 10. Tech Stack (To Be Decided)

- **Language:** Python (typical for data + APIs).
- **Broker API:** IBKR Client Portal API or TWS API.
- **Data:** Yahoo Finance, Alpha Vantage, or broker data.
- **Scheduling:** Cron or systemd timer.
- **Storage:** SQLite or CSV for logs and state.

---

## 11. Next Steps

1. Set up development environment (Python, IBKR paper account).
2. Implement Phase 1: data fetch + signal computation.
3. Implement Phase 2: rules engine + paper trading simulator.
4. Backtest on historical data.
5. Run paper trading for 3–6 months.
6. Add calendar filter (Phase 2 data).
7. Integrate IBKR API; go live with small size.
8. Add macro filter (Phase 3 data) when comfortable.

---

*Document created from brainstorming session. Revise as the project evolves.*
