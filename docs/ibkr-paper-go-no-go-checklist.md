# IBKR Paper Rollout: Go/No-Go Checklist

Use this checklist after all readiness tickets are complete and before enabling
any automated IBKR paper execution. One operator should be able to run this
from top to bottom and document the decision.

## 1) Prerequisites and Linked Tickets

- [ ] All required readiness tickets are linked in this section.
- [ ] All linked readiness tickets are in a completed state.
- [ ] Branch/release candidate is fixed (commit SHA recorded).

Linked tickets:

- [ ] `KUA-__`
- [ ] `KUA-__`
- [ ] `KUA-__`

Evidence:

- Release candidate SHA: `________________________`
- Verification timestamp (UTC): `________________________`
- Operator: `________________________`

## 2) Hard Go/No-Go Criteria

All criteria below must pass for a **GO** decision.

- [ ] `pytest tests/` passes on the release candidate.
- [ ] `ruff check .` passes.
- [ ] `mypy trading_bot/ main.py` passes.
- [ ] Guardrails are confirmed enabled:
  - [ ] `DRYRUN=true` for dry-run validation.
  - [ ] `IBKR_ENABLE=false` during dry-run validation.
- [ ] Strategy and risk settings are explicitly reviewed:
  - [ ] `SIGNAL_STRATEGY`
  - [ ] `STOP_LOSS_PCT`
  - [ ] `POSITION_ALLOCATION_PCT`
  - [ ] `PORTFOLIO_VALUE`

Evidence:

- Test/lint/typecheck run logs: `________________________`
- Config review notes: `________________________`

## 3) Environment and Config Verification

Validate `.env` against `.env.example` and confirm paper trading values.

- [ ] `.env` exists and is not committed to git.
- [ ] `IBKR_HOST` points to expected host (usually `127.0.0.1`).
- [ ] `IBKR_PORT=7497` (paper trading).
- [ ] `IBKR_CLIENT_ID` is set and not conflicting with other clients.
- [ ] `IBKR_ACCOUNT` matches paper account (or documented as default).
- [ ] `DRYRUN` behavior verified:
  - [ ] `DRYRUN=true` logs-only mode confirmed.
  - [ ] `DRYRUN=false` is not used until explicit GO decision.

Evidence:

- Sanitized config screenshot/snippet: `________________________`
- IBKR paper account verification notes: `________________________`

## 4) End-to-End Paper Dry Run

Run an operational dry run and confirm expected logs/behavior.

Suggested command:

```bash
DRYRUN=true python run_weekly.py
```

Checklist:

- [ ] Command exits successfully.
- [ ] Data fetch succeeds for configured symbols.
- [ ] Signals are generated and logged.
- [ ] Order-intent logs are present without placing real orders.
- [ ] No unhandled exceptions in logs.

Evidence:

- Dry-run command used: `________________________`
- Log location (file/journal): `________________________`
- Log excerpt reference: `________________________`

## 5) Rollback and Incident Plan

Rollback must be clear before deciding GO.

- [ ] Immediate rollback action documented (disable scheduler/timer and keep
      `DRYRUN=true`).
- [ ] Operator knows where service logs are inspected.
- [ ] Owner/on-call contact documented.

Rollback commands (systemd user setup):

```bash
systemctl --user disable --now trading-bot.timer
systemctl --user stop trading-bot.service
```

Evidence:

- Rollback owner: `________________________`
- Incident escalation path: `________________________`

## 6) Final Decision and Sign-Off

Use exactly one decision and include links to evidence.

- [ ] **GO** (all checks passed)
- [ ] **NO-GO** (one or more checks failed)

Required sign-off fields:

- Decision timestamp (UTC): `________________________`
- Decision owner: `________________________`
- Approver(s): `________________________`
- Evidence links: `________________________`
- Follow-up actions (if NO-GO): `________________________`

## Linear Ticket Comment Template

Paste this into the deployment ticket comment (for example `KUA-63`) when the
checklist run is complete:

```text
Deployment decision: GO|NO-GO
Release candidate SHA: <sha>
Checklist document: docs/ibkr-paper-go-no-go-checklist.md

Evidence:
- Test/lint/typecheck: <link or log reference>
- Config verification: <link or screenshot reference>
- Paper dry run output: <link or log reference>
- Rollback readiness confirmation: <notes>

Operator: <name>
Approver(s): <name(s)>
Timestamp (UTC): <timestamp>

Notes:
- <optional note 1>
- <optional note 2>
```
