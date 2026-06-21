"""Phase 3 orchestration: translate -> confirm -> (optionally) correct.

`translate()` and `correct()` never run a backtest — they only produce an IR
and a human-readable restatement for the user to confirm. `confirm()` is the
single, explicit place a backtest is triggered, and it re-validates the IR
against the schema defensively before handing it to the safe interpreter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.engine.backtest import BacktestResult, run_ir_backtest
from app.translation.defaults import Assumption
from app.translation.interpreter import validate_ir
from app.translation.renderer import render_confirmation
from app.translation.translator import AnthropicLLMClient, LLMClient, translate_to_ir

# Robinhood-tier retail cost model (matches Phase 1's `phase1_slice.py`):
# ~0 commission, but slippage/spread is real.
RETAIL_FEES = 0.0
RETAIL_SLIPPAGE = 0.0005


@dataclass
class TranslationResponse:
    status: str  # "ok" | "unsupported" | "error"
    ir: dict | None = None
    assumptions: list[Assumption] = field(default_factory=list)
    restatement: str | None = None
    message: str | None = None
    retries: int = 0


def _default_llm_client() -> LLMClient:
    return AnthropicLLMClient()


def translate(nl_text: str, llm_client: LLMClient | None = None) -> TranslationResponse:
    """NL -> (IR, assumptions, restatement). Never runs a backtest."""
    client = llm_client or _default_llm_client()
    result = translate_to_ir(nl_text, client)

    if result.status != "ok":
        return TranslationResponse(
            status=result.status,
            message=result.message,
            retries=len(result.attempts) - 1 if result.attempts else 0,
        )

    restatement = render_confirmation(result.full_ir, result.assumptions)
    return TranslationResponse(
        status="ok",
        ir=result.full_ir,
        assumptions=result.assumptions,
        restatement=restatement,
        retries=len(result.attempts) - 1,
    )


def correct(
    original_nl: str,
    prior_ir: dict,
    correction_text: str,
    llm_client: LLMClient | None = None,
) -> TranslationResponse:
    """Re-translate with a free-text correction layered onto the original request.

    No structured field editor in v1 — the user's correction is plain text,
    appended as additional context alongside the prior interpretation so the
    model can see what it got wrong.
    """
    combined_nl = (
        f"{original_nl}\n\n"
        f"I previously translated this as: {prior_ir}\n\n"
        f"The user says that's wrong, with this correction: {correction_text}\n"
        "Produce a corrected sparse IR for the ORIGINAL request, taking the "
        "correction into account."
    )
    return translate(combined_nl, llm_client)


def confirm(
    ir: dict,
    price_data: pd.DataFrame,
    *,
    fees: float = RETAIL_FEES,
    slippage: float = RETAIL_SLIPPAGE,
) -> BacktestResult:
    """Run the backtest for a user-confirmed IR. The only place this happens."""
    validate_ir(ir)
    return run_ir_backtest(ir, price_data, fees=fees, slippage=slippage)
