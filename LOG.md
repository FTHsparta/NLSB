# Build Log — NLSB

A running log of decisions, learnings, and progress on the Natural Language Strategy Backtester.

---

## 2026-05-30 — Set up repo and initial scoping

Initialized the GitHub repo with README, LOG, and basic structure (`/backend`, `/frontend`, `/docs`). 

Locked v1 scope: stocks/ETFs + crypto, daily bars only, no user accounts, Python backend + Next.js frontend. Explicitly out of scope: intraday data, live trading, multi-asset strategies, portfolio backtesting.

Decided on Python for backend because the quant ecosystem (pandas, vectorbt, scipy) lives there. Considered Streamlit for speed but went with FastAPI + Next.js for a real product feel.

Next: read the Lopez de Prado overfitting paper before writing any code, then sketch architecture.

---

## 2026-05-28 — Built Systems
Created LOG.md file and template and began sketching out an overview of the system and the different components that interact with each other. 
Next: Read Lopez De Prado's research and finish the sketch of the system.
