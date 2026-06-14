# Architecture

```
[Frontend (Next.js)]
       │  POST /api/backtest  { strategy_text, ticker, asset_class, date_range, params }
       ▼
[Backend API (FastAPI)]
       ├──► [LLM Translation Service]  NL text → strategy JSON (IR)
       │         └─ validate JSON against schema; if invalid, send the
       │            validation error back to the LLM and re-translate (retry loop)
       ├──► [Market Data Service]  cache → yfinance/ccxt → cleaned DataFrame
       ├──► [Backtest Engine]  IR + data → baseline metrics (via vectorbt)
       ├──► [Robustness Module]  walk-forward, param sweeps, deflated Sharpe, regime test
       ├──► [Storage (SQLite)]  save full result, return shareable id
       ▼
[Frontend]  renders baseline ("optimistic") view + honest robustness verdict
```

## Request flow

1. Frontend packages strategy text + ticker/params, POSTs to `/api/backtest`.
2. Backend sends strategy text to the LLM Translation Service.
3. LLM returns a structured strategy spec (JSON IR); backend validates it
   against the schema. On invalid JSON/schema failure, re-prompt the LLM with
   the specific error (bounded retries, e.g. 2).
4. Backend asks the Market Data Service for historical data; service checks
   cache, fetches from yfinance/ccxt on miss, returns a cleaned DataFrame.
5. Backend passes IR + data to the Backtest Engine → baseline results.
6. Backend passes IR + data to the Robustness Module → walk-forward,
   parameter sweeps, statistical adjustments (slow part).
7. Backend assembles results (baseline + robustness), saves to Storage,
   returns to frontend.
8. Frontend renders both the optimistic metrics and the honest verdict.

## Security boundary: no LLM-generated code execution

The LLM never produces executable code. It produces a JSON intermediate
representation (IR) validated against a strict schema. A safe interpreter
in our codebase (`backend/app/engine/`) is the only thing that turns IR into
vectorbt signals. `exec`/`eval` on model output is never used. See `LOG.md`
for the entry documenting this decision.

## Naive baseline engine

`backend/app/engines/naive/` holds the hand-rolled RSI backtester (pre-vectorbt).
It is kept as a deliberate point of comparison — discrepancies between it and
the vectorbt production engine illustrate the project's thesis that naive
backtests overstate performance.
