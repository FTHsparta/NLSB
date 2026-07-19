"""HTTP boundary for the translate -> confirm pipeline.

Mirrors the guarantee `app.translation.service` already enforces in Python:
`/translate` and `/correct` call only `service.translate`/`service.correct`,
neither of which has any code path to a backtest. `/confirm` is the sole
route that calls `service.confirm_robustness`, which is the sole place a run
happens. This module composes existing service/robustness functions -- it
does not reimplement translation, defaulting, rendering, or backtest logic.

Public-exposure hardening (Phase 8A) lives in `app.abuse`: every LLM-calling
route passes the per-IP rate limiter, the daily spend breaker, and the input
size cap -- in that order -- before the Anthropic client is reachable, and
every external-call failure is mapped to a plain-English error with no stack
trace crossing the boundary. None of it changes the security boundary: the
LLM still emits only validated IR JSON and no model-emitted code is executed.
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()


import logging
import os
import time
from typing import Any

import jsonschema
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi.errors import RateLimitExceeded

from app import abuse
from app.abuse import (
    body_length_exceeds_cap,
    confirm_rate_limit,
    enforce_ir_complexity,
    enforce_text_size,
    enforce_ticker,
    limiter,
    llm_rate_limit,
    spend_breaker,
)
from app.data.market_data import InsufficientDataError, fetch_daily_bars
from app.translation import service
from app.translation.defaults import Assumption, DefaultingError
from app.translation.interpreter import IRInterpreterError
from app.translation.translator import LLMClient

abuse.configure_logging()
logger = logging.getLogger("app.main")
request_logger = logging.getLogger("app.request")

def docs_enabled() -> bool:
    """Auto-docs are a dev affordance; in production they hand any visitor
    the full machine-readable API surface (openapi.json matters as much as
    the two UIs). NLSB_ENV follows the NLSB_* env pattern from `app.abuse`;
    only the literal value "production" flips this off -- unset/anything
    else keeps the local dev experience unchanged."""
    return os.environ.get("NLSB_ENV", "").lower() != "production"


_docs = docs_enabled()
app = FastAPI(
    title="NLSB API",
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)


# --- CORS (Phase 10) ---------------------------------------------------------
#
# In local dev the Next.js rewrite proxy makes every request same-origin, so
# none of this fires. In the deployed topology (frontend on Vercel, backend on
# Render/Railway, separate domains) the browser calls this API cross-origin
# and needs these headers. Origins come from ALLOWED_ORIGINS (comma-separated,
# read once at startup); methods/headers are the minimum the actual routes
# use (GET /health, POST + JSON body on the other three). Credentials stay
# off -- nothing here uses cookies or auth headers.

_DEV_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def allowed_origins() -> list[str]:
    """Parse ALLOWED_ORIGINS; fall back to the localhost dev origins when
    unset/empty. A literal "*" entry is dropped (with a warning): a wildcard
    is never a valid non-default configuration for this API."""
    raw = os.environ.get("ALLOWED_ORIGINS", "")
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    if "*" in origins:
        logging.getLogger("app.main").warning(
            "ALLOWED_ORIGINS contained '*'; wildcard origins are not honored"
        )
        origins = [o for o in origins if o != "*"]
    return origins or list(_DEV_ORIGINS)


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Rate limiter wiring: slowapi reads the limiter off app.state and raises
# RateLimitExceeded, which we render as a plain-English 429 JSON body.
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests — please slow down and try again in a minute."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Final net: any exception not already mapped to an HTTP status becomes a
    generic 500 with NO traceback in the body. The real exception (with
    traceback) goes to the server log only."""
    logger.exception("unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again later."},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Body-size cap (all routes): reject an over-large declared Content-Length
    # before the body is parsed. The equivalent of Phase 8A's text cap, now
    # covering /confirm's client-supplied IR too.
    if body_length_exceeds_cap(request.headers.get("content-length")):
        request_logger.warning(
            "%s %s -> 413 (body too large: %s bytes)",
            request.method,
            request.url.path,
            request.headers.get("content-length"),
        )
        return JSONResponse(
            status_code=413,
            content={"detail": "Request body is too large. Please send a smaller request."},
        )

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    request_logger.info(
        "%s %s -> %d (%.1f ms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.get("/health")
def health() -> dict:
    """Trivial and fast on purpose: platform health checks poll this. The
    readiness detail is a BOOLEAN ONLY -- never the key, a prefix, or any
    other derivative of it (INV-2)."""
    return {
        "status": "ok",
        "anthropic_key_present": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


# --- Dependencies (overridden in tests to avoid real network/LLM calls) ---


def get_llm_client() -> LLMClient | None:
    """None tells `service.translate`/`service.correct` to construct their
    own default (real) Anthropic client. Tests override this to inject a
    fake client instead."""
    return None


def get_price_fetcher():
    """The real market-data fetch. Tests override this to avoid a network
    call and to control exactly what price history a confirm run sees."""
    return fetch_daily_bars


# --- Shared payload shapes ---


class AssumptionPayload(BaseModel):
    field: str
    value: Any = None
    reason: str
    severity: str

    @classmethod
    def from_assumption(cls, a: Assumption) -> "AssumptionPayload":
        return cls(field=a.field, value=a.value, reason=a.reason, severity=a.severity)

    def to_assumption(self) -> Assumption:
        return Assumption(field=self.field, value=self.value, reason=self.reason, severity=self.severity)


class TranslationPayload(BaseModel):
    status: str
    ir: dict | None = None
    assumptions: list[AssumptionPayload] = []
    restatement: str | None = None
    message: str | None = None
    retries: int = 0

    @classmethod
    def from_response(cls, result: service.TranslationResponse) -> "TranslationPayload":
        return cls(
            status=result.status,
            ir=result.ir,
            assumptions=[AssumptionPayload.from_assumption(a) for a in result.assumptions],
            restatement=result.restatement,
            message=result.message,
            retries=result.retries,
        )


def _run_llm(action: str, call):
    """Invoke an LLM-backed service call, mapping any failure to a 502 with a
    plain-English detail (the real exception is logged). /translate and
    /correct have no external dependency other than the model, so any raised
    exception here is a transport/provider failure, never a strategy problem."""
    try:
        return call()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("LLM call failed during %s", action)
        raise HTTPException(
            status_code=502,
            detail="The translation service is temporarily unavailable. Please try again shortly.",
        ) from exc


# --- /translate, /correct: NEVER reach the backtester ---


class TranslateRequest(BaseModel):
    nl_text: str


@app.post("/translate", response_model=TranslationPayload)
@llm_rate_limit
def translate_route(
    request: Request,
    req: TranslateRequest,
    llm_client: LLMClient | None = Depends(get_llm_client),
) -> TranslationPayload:
    # Gate order (INV-1): rate limiter (decorator) -> spend breaker -> size cap.
    spend_breaker.check()
    enforce_text_size(req.nl_text)
    spend_breaker.record()
    result = _run_llm("translate", lambda: service.translate(req.nl_text, llm_client=llm_client))
    return TranslationPayload.from_response(result)


class CorrectRequest(BaseModel):
    original_nl: str
    prior_ir: dict
    correction_text: str


@app.post("/correct", response_model=TranslationPayload)
@llm_rate_limit
def correct_route(
    request: Request,
    req: CorrectRequest,
    llm_client: LLMClient | None = Depends(get_llm_client),
) -> TranslationPayload:
    spend_breaker.check()
    enforce_text_size(req.original_nl, req.correction_text)
    spend_breaker.record()
    result = _run_llm(
        "correct",
        lambda: service.correct(req.original_nl, req.prior_ir, req.correction_text, llm_client=llm_client),
    )
    return TranslationPayload.from_response(result)


# --- /confirm: the ONLY route that runs anything ---


class ConfirmRequest(BaseModel):
    ir: dict
    assumptions: list[AssumptionPayload] = []
    ticker: str
    start: str
    end: str | None = None


@app.post("/confirm")
@confirm_rate_limit
def confirm_route(
    request: Request, req: ConfirmRequest, price_fetcher=Depends(get_price_fetcher)
) -> dict:
    # Structural cap BEFORE the recursive schema validator sees the IR, so a
    # hostile deeply-nested tree fails fast with a clean 422 instead of a
    # RecursionError-driven 500. Cheap; runs before any price fetch.
    enforce_ir_complexity(req.ir)
    enforce_ticker(req.ticker)

    try:
        price_data = price_fetcher(req.ticker, req.start, req.end)
    except InsufficientDataError as exc:
        # No usable data (bad ticker, empty range, delisting gaps) -- a
        # client-fixable condition, named plainly.
        raise HTTPException(
            status_code=422,
            detail=f"No usable price data for {req.ticker!r}: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        # Provider/network failure fetching prices -- not the caller's fault.
        logger.exception("price fetch failed for %s", req.ticker)
        raise HTTPException(
            status_code=502,
            detail=f"Couldn't fetch price data for {req.ticker!r} right now. Please try again shortly.",
        ) from exc

    assumptions = [a.to_assumption() for a in req.assumptions]
    try:
        return service.confirm_robustness(req.ir, price_data, assumptions)
    except (IRInterpreterError, DefaultingError, jsonschema.ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
