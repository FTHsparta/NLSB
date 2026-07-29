"""Phase 3 orchestration: translate -> confirm -> (optionally) correct.

`translate()` and `correct()` never run a backtest — they only produce an IR
and a human-readable restatement for the user to confirm. `confirm()` is the
single, explicit place a backtest is triggered, and it re-validates the IR
against the schema defensively before handing it to the safe interpreter.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import jsonschema
import pandas as pd

from app.engine.backtest import BacktestResult, run_ir_backtest
from app.robustness.robustness import run_robustness
from app.translation.cache import cache_key, translation_cache
from app.translation.defaults import Assumption
from app.translation.interpreter import IRInterpreterError, compute_ir_warmup, validate_ir
from app.translation.renderer import render_confirmation
from app.translation.translator import (
    PROMPT_SCHEMA_VERSION,
    AnthropicLLMClient,
    LLMClient,
    active_model_name,
    translate_to_ir,
)

logger = logging.getLogger(__name__)

# Robinhood-tier retail cost model (matches Phase 1's `phase1_slice.py`):
# ~0 commission, but slippage/spread is real.
RETAIL_FEES = 0.0
RETAIL_SLIPPAGE = 0.0005

# A validated IR can still be unrunnable against the actual data: if an
# indicator's warmup consumes (nearly) the whole price history -- a period
# larger than the number of bars, or a date range shorter than the warmup --
# the effective window is empty and the downstream stats raise deep in the
# engine. Guard for it explicitly so it surfaces as a clean, named error
# instead of an uncaught 500. Two bars is the floor any return/stat needs.
MIN_EFFECTIVE_BARS = 2


def _require_runnable_window(ir: dict, price_data: pd.DataFrame) -> None:
    warmup = compute_ir_warmup(ir)
    effective = len(price_data) - warmup
    if effective < MIN_EFFECTIVE_BARS:
        raise IRInterpreterError(
            f"Indicator warmup needs {warmup} bars but only {len(price_data)} price "
            f"bars are available, leaving {max(effective, 0)} to backtest. Use a longer "
            "date range or a shorter indicator period."
        )


def unsimulated_risk_reason(ir: dict) -> str | None:
    """Reason to reject *ir*, or None if it carries no stop-loss/take-profit.

    The IR schema accepts `risk.stop_loss_pct`/`take_profit_pct`, but the
    interpreter never reads `ir["risk"]` and the engine never places a
    stop/target order (`_build_ir_portfolio` passes no `sl_stop`/`tp_stop`
    to vectorbt). Running such an IR would report results for a DIFFERENT
    strategy than the one the user stated — so any non-null stop/target is
    rejected here, deterministically, in our code. This must never be left
    to the translator prompt: a stop-bearing IR is schema-valid, so the
    LLM has no reason to self-reject it.
    """
    risk = ir.get("risk")
    if not isinstance(risk, dict):
        return None
    stated = [
        label
        for key, label in (("stop_loss_pct", "a stop-loss"), ("take_profit_pct", "a take-profit"))
        if risk.get(key) is not None
    ]
    if not stated:
        return None
    what = " and ".join(stated)
    return (
        f"This strategy includes {what}, and Deflate doesn't simulate stop-loss or "
        "take-profit orders yet. Running it anyway would report results for a "
        "different strategy than the one you described — one that never exits at "
        "your stop or target. Restate it without the stop/target, or use a "
        "signal-based exit instead (e.g. \"sell when RSI goes above 70\")."
    )


def _reject_unsimulated_risk(ir: dict) -> None:
    """`unsimulated_risk_reason` as a raise — the /confirm-side guard, so a
    stop-bearing IR POSTed directly to the API (bypassing translate) can
    never produce results either."""
    reason = unsimulated_risk_reason(ir)
    if reason is not None:
        raise IRInterpreterError(reason)


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


def _cache_key_for(nl_text: str) -> str:
    return cache_key(nl_text, model=active_model_name(), version=PROMPT_SCHEMA_VERSION)


def _cached_translation(nl_text: str) -> TranslationResponse | None:
    """A previously-validated response for this exact request, or None.

    The cache is a cost optimization, NEVER a trust boundary: the stored IR
    goes back through the same schema validator a fresh translation does. An
    entry that no longer validates (a schema change, a version bump that was
    forgotten) is evicted and the caller translates fresh rather than being
    served something that would fail later at /confirm.
    """
    key = _cache_key_for(nl_text)
    cached = translation_cache.get(key)
    if cached is None:
        return None
    try:
        validate_ir(cached.ir)
    except (jsonschema.ValidationError, IRInterpreterError, TypeError):
        logger.warning("evicting cached translation that no longer validates")
        translation_cache.evict(key)
        return None
    return cached


def translate(
    nl_text: str,
    llm_client: LLMClient | None = None,
    *,
    before_llm: Callable[[], None] | None = None,
) -> TranslationResponse:
    """NL -> (IR, assumptions, restatement). Never runs a backtest.

    `before_llm` is the spend gate: it runs if and only if this call is about
    to invoke the model, so a cache hit costs no daily budget (no API call
    happened). It raises to refuse -- the HTTP layer passes
    `abuse.enforce_spend_budget`, whose 503 propagates untouched.
    """
    cached = _cached_translation(nl_text)
    if cached is not None:
        logger.info("translate: cache hit, skipping the model")
        return cached

    if before_llm is not None:
        before_llm()

    client = llm_client or _default_llm_client()
    result = translate_to_ir(nl_text, client)

    if result.status != "ok":
        return TranslationResponse(
            status=result.status,
            message=result.message,
            retries=len(result.attempts) - 1 if result.attempts else 0,
        )

    # Deterministic post-validation gate check: a schema-valid IR can still
    # describe something the engine won't honestly run (a stop/target). This
    # runs BEFORE the restatement is built, so a stop-bearing IR never
    # becomes a confirmable gate payload — it reuses the existing
    # "unsupported" surface instead of confirming a strategy that wouldn't run.
    risk_reason = unsimulated_risk_reason(result.full_ir)
    if risk_reason is not None:
        return TranslationResponse(
            status="unsupported",
            message=risk_reason,
            retries=len(result.attempts) - 1 if result.attempts else 0,
        )

    restatement = render_confirmation(result.full_ir, result.assumptions)
    response = TranslationResponse(
        status="ok",
        ir=result.full_ir,
        assumptions=result.assumptions,
        restatement=restatement,
        retries=len(result.attempts) - 1,
    )
    # ONLY the fully-validated success path is cached: never a failure, never
    # an "unsupported" verdict, never a partial result. The whole response is
    # stored (IR + assumptions + restatement) so a hit is byte-identical at
    # the API boundary -- the gate's stated-vs-assumed display reads the
    # assumptions list, and a hit that dropped it would silently change what
    # the user is asked to confirm.
    translation_cache.put(_cache_key_for(nl_text), response)
    return response


def correct(
    original_nl: str,
    prior_ir: dict,
    correction_text: str,
    llm_client: LLMClient | None = None,
    *,
    before_llm: Callable[[], None] | None = None,
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
    # Caching and the spend gate both ride on the combined text, so a repeated
    # identical correction is as free as a repeated identical translation.
    return translate(combined_nl, llm_client, before_llm=before_llm)


def confirm(
    ir: dict,
    price_data: pd.DataFrame,
    *,
    fees: float = RETAIL_FEES,
    slippage: float = RETAIL_SLIPPAGE,
) -> BacktestResult:
    """Run the backtest for a user-confirmed IR. The only place this happens."""
    validate_ir(ir)
    _reject_unsimulated_risk(ir)
    return run_ir_backtest(ir, price_data, fees=fees, slippage=slippage)


def confirm_robustness(
    ir: dict,
    price_data: pd.DataFrame,
    assumptions: list[Assumption],
    *,
    fees: float = RETAIL_FEES,
    slippage: float = RETAIL_SLIPPAGE,
) -> dict:
    """Run the full robustness suite for a user-confirmed IR (or the no-exit
    short-circuit) and return the `RESULT_KEYS` dict. Like `confirm()`, this
    is the only place a run happens -- `translate()`/`correct()` have no code
    path that reaches it.

    `assumptions` must be the list `apply_defaults` produced for this exact
    IR (round-tripped from the prior translate/correct response) -- whether
    this is a no-exit strategy is read off the SEVERITY_WARNING `exit`
    assumption, not re-derived from the IR alone.
    """
    validate_ir(ir)
    _reject_unsimulated_risk(ir)
    _require_runnable_window(ir, price_data)
    return run_robustness(ir, price_data, assumptions, fees=fees, slippage=slippage)
