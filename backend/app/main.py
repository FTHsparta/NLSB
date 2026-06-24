"""HTTP boundary for the translate -> confirm pipeline.

Mirrors the guarantee `app.translation.service` already enforces in Python:
`/translate` and `/correct` call only `service.translate`/`service.correct`,
neither of which has any code path to a backtest. `/confirm` is the sole
route that calls `service.confirm_robustness`, which is the sole place a run
happens. This module composes existing service/robustness functions -- it
does not reimplement translation, defaulting, rendering, or backtest logic.
"""

from __future__ import annotations

from typing import Any

import jsonschema
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from app.data.market_data import fetch_daily_bars
from app.translation import service
from app.translation.defaults import Assumption, DefaultingError
from app.translation.interpreter import IRInterpreterError
from app.translation.translator import LLMClient

app = FastAPI(title="NLSB API")


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


# --- /translate, /correct: NEVER reach the backtester ---


class TranslateRequest(BaseModel):
    nl_text: str


@app.post("/translate", response_model=TranslationPayload)
def translate_route(
    req: TranslateRequest, llm_client: LLMClient | None = Depends(get_llm_client)
) -> TranslationPayload:
    result = service.translate(req.nl_text, llm_client=llm_client)
    return TranslationPayload.from_response(result)


class CorrectRequest(BaseModel):
    original_nl: str
    prior_ir: dict
    correction_text: str


@app.post("/correct", response_model=TranslationPayload)
def correct_route(
    req: CorrectRequest, llm_client: LLMClient | None = Depends(get_llm_client)
) -> TranslationPayload:
    result = service.correct(req.original_nl, req.prior_ir, req.correction_text, llm_client=llm_client)
    return TranslationPayload.from_response(result)


# --- /confirm: the ONLY route that runs anything ---


class ConfirmRequest(BaseModel):
    ir: dict
    assumptions: list[AssumptionPayload] = []
    ticker: str
    start: str
    end: str | None = None


@app.post("/confirm")
def confirm_route(req: ConfirmRequest, price_fetcher=Depends(get_price_fetcher)) -> dict:
    try:
        price_data = price_fetcher(req.ticker, req.start, req.end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    assumptions = [a.to_assumption() for a in req.assumptions]
    try:
        return service.confirm_robustness(req.ir, price_data, assumptions)
    except (IRInterpreterError, DefaultingError, jsonschema.ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
