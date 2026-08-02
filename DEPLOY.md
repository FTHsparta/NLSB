# Deploying NLSB

Two services, separate domains:

```
┌─────────────────────┐         ┌──────────────────────────┐
│  Frontend (Vercel)  │  HTTPS  │  Backend (Render/Railway)│
│  Next.js            ├────────►│  FastAPI + uvicorn       │
│  NEXT_PUBLIC_API_   │  CORS   │  ALLOWED_ORIGINS lists   │
│  BASE_URL → backend │         │  the frontend origin     │
└─────────────────────┘         └──────────────────────────┘
```

The browser calls the backend directly (cross-origin); the backend's
`ALLOWED_ORIGINS` must therefore list the deployed frontend origin. In local
dev neither env var is set and everything falls back to the Next.js rewrite
proxy (`next.config.ts`) against `http://127.0.0.1:8000` — same-origin, no
CORS involved.

## Environment variables

| Variable | Default | Purpose | Set where |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | *(none)* | Anthropic API key for `/translate` & `/correct`. Secret — dashboard only, never committed. `/health` reports its presence as a boolean. | Backend (both platforms); local: `backend/.env` |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Model used by the translator. | Backend (optional) |
| `ALLOWED_ORIGINS` | `http://localhost:3000, http://127.0.0.1:3000` | Comma-separated CORS allowlist. Set to the deployed frontend origin(s). A literal `*` is ignored (never honored). | Backend |
| `PORT` | *(platform-injected)* | Port uvicorn binds to in production. | Backend — set automatically by Render/Railway |
| `NLSB_RATE_LIMIT_ENABLED` | `true` | Master switch for per-IP rate limiting (Phase 8A). | Backend (leave default in prod) |
| `NLSB_TRUST_PROXY_HEADERS` | `false` | Key the per-IP limiter on the leftmost `X-Forwarded-For` entry instead of the TCP peer. **Set to `true` on Render/Railway** — behind their edge proxy the peer is the proxy for every visitor, so leaving it off puts all traffic in one bucket. Leave `false` anywhere the process is directly reachable (the header is client-spoofable). | Backend (prod: `true`) |
| `NLSB_RATE_LIMIT_LLM_PER_MIN` | `10` | Shared per-IP per-minute budget for `/translate` + `/correct`. | Backend (optional) |
| `NLSB_RATE_LIMIT_LLM_PER_DAY` | `60` | Shared per-IP daily budget for `/translate` + `/correct`. | Backend (optional) |
| `NLSB_RATE_LIMIT_CONFIRM_PER_MIN` | `20` | Per-IP per-minute limit on `/confirm`. | Backend (optional) |
| `NLSB_LLM_DAILY_CAP` | `200` | Process-wide daily cap on LLM-calling requests (spend breaker → 503). | Backend (optional) |
| `NLSB_MAX_NL_CHARS` | `2000` | Max chars of free-text sent to the LLM (→ 422). | Backend (optional) |
| `NLSB_MAX_BODY_BYTES` | `65536` | Request body size cap, all routes (→ 413). | Backend (optional) |
| `NLSB_MAX_IR_DEPTH` | `40` | Max client-supplied IR nesting depth at `/confirm` (→ 422). | Backend (optional) |
| `NLSB_MAX_IR_NODES` | `2000` | Max client-supplied IR node count at `/confirm` (→ 422). | Backend (optional) |
| `NLSB_EVENTS_ENABLED` | `true` | Record aggregate funnel counts (Phase 12E). | Backend (optional) |
| `NLSB_DATA_DIR` | `/data` | Directory holding `events.sqlite3`. **Must match the Railway volume's mount path** — see below. | Backend |
| `NLSB_EVENTS_TOKEN` | *(unset)* | Shared secret for the event read routes. **Unset ⇒ both routes 404** (fails closed). Secret — dashboard only. | Backend |
| `NLSB_RATE_LIMIT_EVENTS_PER_MIN` | `60` | Per-IP limit on `POST /events`. The IP buckets the limit and is never stored. | Backend (optional) |
| `NLSB_LOG_LEVEL` | `INFO` | Stdlib logging level. | Backend (optional) |
| `NLSB_RUN_LIVE_SMOKE` | *(unset)* | Dev/manual only: opts in to the live-LLM smoke script (`backend/tests/smoke_injection_live.py`). Never set in CI or prod. | Local dev only |
| `NEXT_PUBLIC_API_BASE_URL` | *(unset → relative paths + dev proxy)* | Backend origin the browser calls, e.g. `https://nlsb-backend.onrender.com`. Build-time inlined — changing it requires a Vercel redeploy. | Frontend (Vercel) |
| `BACKEND_ORIGIN` | `http://127.0.0.1:8000` | Dev-only: where `next.config.ts` rewrites proxy `/translate` `/correct` `/confirm`. Irrelevant once `NEXT_PUBLIC_API_BASE_URL` is set. | Frontend (local dev only) |

Rate limits are per-process and in-memory (Phase 8A design note): run a
**single instance / single worker** unless you move the limiter storage to a
shared store like Redis.

## Backend — Render

Connect the repo and let the checked-in [render.yaml](render.yaml) blueprint
drive it, or enter manually:

| Setting | Value |
|---|---|
| Root directory | `backend` |
| Build command | `pip install -r requirements.txt -c requirements.lock.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |
| Python version | env var `PYTHON_VERSION=3.14.2` (Render's mechanism; `backend/.python-version` also present and read) |

Then set `ANTHROPIC_API_KEY` and `ALLOWED_ORIGINS` in the dashboard.

## Backend — Railway

| Setting | Value |
|---|---|
| Root directory | `backend` |
| Start command | from `backend/Procfile`: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Build | auto-detected; installs with pip — override install command to `pip install -r requirements.txt -c requirements.lock.txt` |
| Python version | `backend/.python-version` (`3.14.2`) — Railway's mechanism |
| Health check path | `/health` (service settings) |

Then set `ANTHROPIC_API_KEY` and `ALLOWED_ORIGINS` in the service variables.

`/health` returns `{"status": "ok", "anthropic_key_present": true|false}` —
the boolean is a readiness detail; it is never the key or any part of it.

### Persistent volume (required for event counts)

Event counting (Phase 12E) writes `events.sqlite3` under `NLSB_DATA_DIR`.
Railway containers have an **ephemeral filesystem**: without a volume the
database is recreated on every deploy and every restart, so the counts silently
reset and the numbers you read are "since the last deploy", not "since launch".
That failure is invisible — the endpoints keep working and keep returning
plausible-looking figures.

1. Add a **Volume** to the backend service.
2. Set its mount path (e.g. `/data`).
3. Set `NLSB_DATA_DIR` to **exactly that mount path**. A mismatch writes to the
   container's own filesystem, which looks identical until a redeploy.

If the directory is unwritable the app does not crash — it logs loudly, sets
`storage_enabled: false` in the summary, and every other route continues
working. Losing counts is acceptable; taking `/translate` and `/confirm` down
because a volume was not mounted is not.

### Reading the numbers

Both read routes require `NLSB_EVENTS_TOKEN`, as `?token=…` or an
`X-Events-Token` header. **Unset ⇒ both return 404**: an unset secret must
never mean "readable by anyone". A wrong token also returns 404 rather than
401, so probing reveals nothing about what exists.

- `GET /events/summary?token=…` — JSON, including `total_backtests_completed`
  and `gate_confirm_rate` as explicit fields.
- `GET /events/summary/page?token=…` — the same numbers as a plain HTML table,
  no client JS, readable on a phone.

## Frontend — Vercel

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Build command | `npm run build` (default) |
| Env var | `NEXT_PUBLIC_API_BASE_URL=https://<backend-domain>` |

After the backend is up, set the backend's `ALLOWED_ORIGINS` to the Vercel
production domain (plus preview domains if you want previews to work against
the real backend).

## Dependency pinning

`backend/requirements.txt` is the human-edited manifest;
`backend/requirements.lock.txt` pins the full transitive closure to the
exact versions the suite was tested against. Always install with
`-r requirements.txt -c requirements.lock.txt`.

**Known unpinnable:** `uvloop` (a `uvicorn[standard]` extra) ships no Windows
wheel, so the Windows-generated lock omits it; on Linux it installs unpinned.
Everything else pins exactly. Regeneration instructions are in the lockfile
header.

## Rollback

Both Render and Railway keep prior deploys: roll back by redeploying the
previous commit (Render: "Rollback" on the deploy list; Railway: redeploy an
earlier deployment from the service's deploy history; Vercel: "Instant
Rollback" / promote a previous deployment). No schema/state migrations exist
in v1, so rolling back is always safe.

## Windows dev gotchas (do not "fix" these in prod configs)

- `from __future__ import annotations` must stay the **first statement** in
  its module (only the docstring may precede it) — reordering imports, e.g.
  moving `load_dotenv()` above it in `app/main.py`, is a syntax error.
- The taskkill port-reset ritual (find the stale uvicorn PID via
  `netstat -ano | findstr :8000`, then `taskkill /PID <pid> /F`) is a
  **dev-only** Windows workaround for a port stuck from a previous reload;
  it has no production equivalent and must never appear in a start command
  or deploy script.
