# Build Log

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
