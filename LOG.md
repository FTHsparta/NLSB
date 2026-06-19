# Build Log

## 2026-06-19 — Phase 1 addendum: buy-and-hold benchmark

Added a reusable `compute_buy_and_hold_metrics(close, warmup, fees, slippage, init_cash) -> BacktestResult` to `app/engine/backtest.py`. It trims the same `warmup` bars as the strategy so the comparison window is identical, applies the same vectorbt cost model (entry slippage on the single buy, no exit since the position is never closed), and returns `BacktestResult` with `win_rate=nan` / `num_trades=0` (trade stats are not meaningful for a single held position).

`phase1_slice.py` now prints three blocks — strategy (with retail costs), strategy (idealized), buy-and-hold — followed by a one-line verdict of annualized excess return and whether the strategy beat or lagged B&H.

**Three new tests (22 total, all green):**
- `test_buy_and_hold_window_matches_strategy` — B&H `start`/`end` matches strategy's effective window on the same close series.
- `test_buy_and_hold_trade_stats_are_not_applicable` — confirms `num_trades == 0` and `win_rate` is NaN.
- `test_strategy_lags_buy_and_hold_on_trending_series` — uses a steadily rising synthetic series where RSI never crosses 30 (strategy never enters, return ≈ 0%) to assert strategy annualized return < B&H annualized return.

## 2026-06-14 — Phase 0/1 kickoff: scaffold, dependency pins, security boundary

**Repo scaffolded from scratch.** No prior `README.md`/`LOG.md`/`docs/` existed,
so they were created as part of this session (per the build prompt's
fallback instruction for a fresh directory).

**Python environment:** the only Python available is **3.14.2**. This is
newer than `vectorbt`'s historically-tested range, so the full dependency
chain was installed and smoke-tested before locking versions. Result: it
works cleanly, including numba JIT compilation. Pinned in
`backend/requirements.txt`:

- `vectorbt==1.0.0`
- `numpy==2.4.6`
- `pandas==2.3.3`
- `numba==0.65.1`
- `llvmlite==0.47.0`
- `scipy==1.17.1`

Verified with a `Portfolio.from_signals` smoke test (synthetic price series,
fees + slippage set) — JIT-compiled numba functions ran without error and
produced sane total return / Sharpe values. `yfinance` data fetch for SPY
(2015–2024, 2264 daily bars) also verified working.

**Note on `yfinance`:** recent versions return a `MultiIndex` column DataFrame
(`('Close', 'SPY')` etc.) even for a single ticker. The market-data layer
flattens this to a simple `Open/High/Low/Close/Volume` frame.

**Security boundary (restated from the build prompt):** the LLM translation
layer (Phase 3+) will produce a JSON intermediate representation only. A safe
interpreter (`backend/app/engine/`) is the sole code path from IR → vectorbt
signals. `exec`/`eval` on model output will never be used. This is a hard
requirement, not an optimization to be relaxed later.

**`docs/architecture.png` → `docs/architecture.md`:** the prompt referenced a
PNG architecture diagram from "earlier scoping" that doesn't exist in this
fresh repo. Substituted a text/ASCII diagram in `docs/architecture.md`
(same content as the prompt's architecture section) — can be replaced with a
rendered image later without changing structure.

## 2026-06-14 — Phase 0 complete

- **Backend:** FastAPI skeleton (`backend/app/main.py`) with `GET /health` →
  `{"status": "ok"}`. Package layout for `translation/`, `data/`, `engine/`,
  `engines/naive/`, `robustness/`, `storage/` created (empty, populated in
  later phases). `pytest` passes (`tests/test_health.py`).
- **Frontend:** `create-next-app` skeleton in `frontend/` — Next.js 16.2.9
  (App Router, Turbopack), TypeScript, Tailwind v4, ESLint. `npm run build`
  succeeds. Added `turbopack.root` to `next.config.ts` because Next.js was
  picking up an unrelated `package-lock.json` in the parent home directory
  as the workspace root.
- **Environment note:** in Git Bash (and this session's shells generally),
  `ComSpec` is unset, which makes `npm run <script>` crash with
  `ERR_INVALID_ARG_TYPE`. Documented the workaround in the README. This is an
  environment quirk, not a project bug — `next build`/`next dev` invoked
  directly work fine.

## 2026-06-14 — Phase 1 complete: dumbest end-to-end slice

Hard-coded strategy (buy SPY when RSI(14) < 30, sell when RSI(14) > 70),
fetched via yfinance, run through vectorbt. `python -m app.phase1_slice`
prints metrics with and without retail costs. 19 tests pass
(`pytest`, `backend/tests/`).

**New modules:**
- `app/data/market_data.py` — `fetch_daily_bars()`: adjusted-close OHLCV via
  yfinance, flattens the MultiIndex columns recent yfinance versions return,
  validates min bar count and rejects suspicious gaps (>10 calendar days).
- `app/engine/indicators.py` — `wilder_rsi()`.
- `app/engine/signals.py` — `rsi_threshold_signals()` (raw conditions) +
  `shift_for_next_bar_execution()` (the no-lookahead shift).
- `app/engine/backtest.py` — `run_rsi_backtest()`: wires indicators → signals
  → `vbt.Portfolio.from_signals()` → `BacktestResult`.

**Design decisions (the correctness requirements, addressed):**

1. **No lookahead bias.** Convention: *signal computed from bar i's close →
   executes at bar i+1's close*. Every raw condition (`rsi < 30`, `rsi > 70`)
   goes through `shift_for_next_bar_execution()` before vectorbt sees it
   (vectorbt fills at the same bar's close by default, so shifting first is
   what makes this next-bar). `test_signals.py::test_no_lookahead_entry_executes_on_bar_after_signal`
   constructs a price series where same-bar vs next-bar fill prices differ
   and asserts the fill is the next-bar price.

2. **Wilder's RSI**, not SMA-of-gains/losses. `wilder_rsi()` seeds the
   average gain/loss with an SMA of the first `period` changes, then applies
   the recursive `(prev*(period-1) + current) / period` smoothing — the same
   "RMA" definition TradingView's `ta.rma()`/built-in RSI uses.
   `test_indicators.py` checks it against an independently-written recursive
   reference implementation, bounds (0-100), saturation on monotonic
   series, and that it diverges from a naive rolling-SMA RSI after the seed
   bar.

3. & 4. **Entry-price tracking / stop-loss persistence** — not yet
   applicable: the Phase 1 strategy has no stop-loss. vectorbt's
   `Portfolio.from_signals` tracks entry price internally and exposes it via
   `trades.records_readable`. Dedicated tests land in **Phase 2** once the IR
   adds `stop_loss`/`take_profit`, using vectorbt's `sl_stop`/`tp_stop`
   (which are entry-price-relative and persist until a fresh entry signal —
   exactly what's required).

5. **Warmup / lookback.** RSI(14) is undefined for the first 14 bars, and the
   no-lookahead shift consumes one more — `run_rsi_backtest` drops the first
   `rsi_period + 1` bars and returns the *actual* tested date range
   (`BacktestResult.start`/`.end`), which `phase1_slice.py` prints. Verified
   by `test_warmup_window_drops_first_period_plus_one_bars`.

6. **Transaction costs.** `run_rsi_backtest` takes `fees`/`slippage` and is
   run twice in `phase1_slice.py` — once at Robinhood-tier retail (0
   commission, 5bps slippage) and once idealized (no costs) — so the cost
   impact is visible side by side.
   `test_costs_reduce_returns_relative_to_no_cost_baseline` asserts the
   cost-adjusted run never beats the no-cost run.

7. **Data sanity.** `fetch_daily_bars` uses `auto_adjust=True` (splits/
   dividends handled via adjusted close), requires ≥252 bars, and rejects
   gaps >10 calendar days. Tested with synthetic data (no live-network
   dependency for the validation logic) plus one live integration test
   against real SPY data.

**Annualization convention.** yfinance's daily index has no fixed pandas
`freq` (weekend/holiday gaps), so vectorbt's own `annualized_return()` /
`sharpe_ratio()` can't infer a `year_freq` and raise. Instead,
`annualized_return = (1 + total_return) ** (252 / num_bars) - 1` and
`sharpe = mean(daily_returns) / std(daily_returns) * sqrt(252)`
(risk-free rate = 0 for v1) — the standard 252-trading-day convention.

**Naive baseline engine (`app/engines/naive/`)** — still empty. The build
prompt says to port the user's existing hand-rolled RSI backtester here as a
comparison baseline; that needs the user's existing code, so it's deferred to
Phase 2 (when the IR/interpreter exist and the "run both engines, report
divergence" script makes sense).

**Live Phase 1 numbers (SPY, 2010-01-26 to 2026-06-12, 4136 bars fetched):**
16 trades either way; with 5bps slippage: total return 265.99% / annualized
8.26% / Sharpe 0.67 / max drawdown -28.32% / win rate 93.75%. Without costs:
271.89% / 8.36% / 0.68 / -28.32% / 93.75%. (Numbers will drift as more bars
accumulate over time — this is a snapshot, not a target to match.)
