# NLSB — Natural Language Strategy Backtester

A backtester for people who want an honest answer.

Describe a trading strategy in plain English (e.g. *"buy SPY when RSI drops
below 30 and the 50-day MA is above the 200-day; sell when RSI exceeds 70"*)
and get back:

1. Standard performance metrics (total return, annualized return, Sharpe,
   max drawdown, win rate).
2. An **honest robustness/overfitting assessment** — walk-forward validation,
   parameter sensitivity, deflated Sharpe ratio, regime testing — translated
   into a plain-English verdict (PASS / SHAKY / LIKELY OVERFIT).

## v1 scope

**In scope:**
- US stocks/ETFs (daily bars, 10+ years) via `yfinance`; crypto (daily bars,
  top ~20 by market cap, Binance) via `ccxt`.
- Natural-language strategy input → structured JSON IR → safe interpreter
  (no LLM-generated code is ever executed).
- Core metrics + robustness module (see above).
- Realistic transaction-cost modeling (commissions ~0, but slippage/spread
  modeled).
- Shareable result URLs. No user accounts.

**Out of scope for v1:** intraday data, live/paper trading, multi-asset
strategies, portfolio backtesting, user accounts, social features.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the component diagram
and request flow.

## Repo structure

```
nlsb/
├── README.md
├── LOG.md                 # dated build log — what was built and why
├── docs/
│   └── architecture.md
├── backend/
│   ├── app/
│   │   ├── main.py         # FastAPI app + routes
│   │   ├── translation/     # LLM service, IR schema, validator, retry loop
│   │   ├── data/             # market data service + caching
│   │   ├── engine/            # vectorbt production engine + safe IR interpreter
│   │   ├── engines/naive/       # hand-rolled baseline engine (comparison)
│   │   ├── robustness/           # walk-forward, sensitivity, DSR, regime, verdict
│   │   └── storage/                # SQLite, save/load shared results
│   ├── tests/               # pytest
│   └── requirements.txt
└── frontend/                # Next.js + Tailwind
```

## Running locally

### Backend

```bash
cd backend
python -m venv .venv
./.venv/Scripts/activate   # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
cp ../.env.example ../.env  # then fill in ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

Health check: `GET http://127.0.0.1:8000/health`

### Phase 1 slice (no server)

```bash
cd backend
./.venv/Scripts/python.exe -m app.phase1_slice
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

(Strategy input UI arrives in Phase 6 — for now this is the default Next.js +
Tailwind v4 + TypeScript scaffold from `create-next-app`.)

> **Git Bash / some shells:** if `npm run <script>` fails with
> `ERR_INVALID_ARG_TYPE: The "file" argument must be of type string. Received undefined`,
> it's because `ComSpec` isn't set in that shell's environment (npm needs it
> to find `cmd.exe`). Set it, e.g. `export ComSpec="C:\\Windows\\System32\\cmd.exe"`,
> or use a regular PowerShell/cmd terminal where it's already set.
