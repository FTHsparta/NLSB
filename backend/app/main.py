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
import time
from typing import Any

import jsonschema
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi.errors import RateLimitExceeded

from app import abuse
from app.abuse import (
    confirm_rate_limit,
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

app = FastAPI(title="NLSB API")

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
    return {"status": "ok"}


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
