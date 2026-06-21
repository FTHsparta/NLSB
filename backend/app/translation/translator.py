"""Natural language -> sparse IR via the Anthropic API.

Security boundary: this module's only output is JSON text. Nothing here
(or anywhere downstream) ever exec/eval's model output. The JSON is parsed
with `json.loads`, defaulted by `app.translation.defaults`, and schema-
validated by `app.translation.interpreter.validate_ir` before anything
touches price data — see `app.translation.service` for the full pipeline.

The model is instructed to emit a *sparse* IR: only the fields the user
explicitly stated, omitting anything it would otherwise have to guess. Our
own code (`defaults.apply_defaults`) fills the gaps, not the model — that's
what makes the "I assumed" list in the confirmation step trustworthy.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Protocol

import jsonschema

from app.translation.defaults import DefaultingError, apply_defaults
from app.translation.interpreter import validate_ir

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_RETRIES = 3

_SYSTEM_PROMPT = """You translate a natural-language trading strategy description into a JSON \
intermediate representation (IR). You output JSON ONLY — no prose, no markdown code fences, \
no explanation before or after. Your entire response must be a single JSON object.

The IR has this shape (fields you are SURE the user stated):
{
  "asset": {"ticker": "<SYMBOL>", "asset_class": "equity" | "etf" | "crypto" | "futures"},
  "indicators": [
    {"id": "<short_identifier>", "type": "RSI" | "SMA" | "EMA",
     "params": {"period": <int>}, "source": "close" | "open" | "high" | "low"}
  ],
  "entry": <condition>,
  "exit": <condition>,
  "position": {"direction": "long", "size": "full"},
  "risk": null | {"stop_loss_pct": <0-1 fraction or null>, "take_profit_pct": <fraction or null>}
}

A <condition> is either:
  {"all_of": [<condition>, ...]}   (AND)
  {"any_of": [<condition>, ...]}   (OR)
  {"left": <operand>, "op": "<" | ">" | "<=" | ">=" | "crosses_above" | "crosses_below", "right": <operand>}

An <operand> is a number, an indicator id (e.g. "rsi14"), or a price field name
("close", "open", "high", "low").

CRITICAL — sparse output: only include a field if the user's text actually implies it.
- If the user doesn't state an indicator's period, OMIT "params" (or "period") entirely —
  do not invent a number.
- If the user doesn't state a source price field for an indicator, OMIT "source".
- If the user doesn't describe an exit at all, OMIT "exit" entirely.
- If the user doesn't state asset_class, OMIT it.
- If the user doesn't mention a stop-loss/take-profit, OMIT "risk" entirely.
- "asset.ticker" and "entry" must always be present — pick the best reading of what the
  user described, using standard trading terminology (e.g. "oversold" commonly means RSI
  below 30) for the comparison VALUES, but still omit fields like period/source you aren't
  told.
- Never invent an indicator id that isn't referenced; every id you create must be used by
  an operand in entry or exit.

UNSUPPORTED REQUESTS: v1 only supports a single asset, daily bars, long-only positions, and
the indicators/operators above. If the request requires intraday data, options, multiple
assets, portfolio allocation, or anything else outside that, respond with ONLY:
{"unsupported": true, "reason": "<short plain-English reason>"}

If a previous attempt was rejected, you will be told exactly why — fix only that problem in \
your next response, still following all the rules above."""


class LLMClient(Protocol):
    def complete(self, *, system: str, user: str) -> str:
        """Return the model's raw text response to a single-turn prompt."""
        ...


class AnthropicLLMClient:
    """Thin wrapper around the Anthropic SDK. Lazily imports `anthropic`."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._model = model or os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def complete(self, *, system: str, user: str) -> str:
        client = self._get_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=2048,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )


@dataclass
class TranslationAttempt:
    raw_response: str
    error: str | None = None


@dataclass
class TranslationResult:
    status: str  # "ok" | "unsupported" | "error"
    sparse_ir: dict | None = None
    full_ir: dict | None = None
    assumptions: list = field(default_factory=list)
    message: str | None = None
    attempts: list[TranslationAttempt] = field(default_factory=list)


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = _FENCE_RE.sub("", text).strip()
    # Defensive fallback: if there's still preamble/trailing prose, take the
    # outermost {...} span.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return text


def translate_to_ir(
    nl_text: str, llm_client: LLMClient, max_retries: int = MAX_RETRIES
) -> TranslationResult:
    """Run the NL -> sparse IR -> defaulted/validated full IR pipeline with retries.

    On each attempt: call the LLM, parse JSON, check for the unsupported
    sentinel, apply defaults, and schema-validate the result. Any failure
    (bad JSON, a DefaultingError, or a jsonschema ValidationError) becomes
    the EXACT error text appended to the next prompt as a correction.
    """
    logger.info("translate_to_ir: nl=%r", nl_text)
    attempts: list[TranslationAttempt] = []
    user_message = nl_text

    for attempt_num in range(1, max_retries + 1):
        raw = llm_client.complete(system=_SYSTEM_PROMPT, user=user_message)
        logger.debug("translate_to_ir: attempt %d raw response=%r", attempt_num, raw)

        try:
            parsed = json.loads(_strip_fences(raw))
        except json.JSONDecodeError as exc:
            error = f"Response was not valid JSON: {exc}"
            attempts.append(TranslationAttempt(raw_response=raw, error=error))
            user_message = _retry_message(nl_text, error)
            logger.warning("translate_to_ir: attempt %d invalid JSON: %s", attempt_num, error)
            continue

        if isinstance(parsed, dict) and parsed.get("unsupported"):
            reason = parsed.get("reason", "This kind of strategy isn't supported in v1.")
            attempts.append(TranslationAttempt(raw_response=raw, error=None))
            logger.info("translate_to_ir: unsupported request: %s", reason)
            return TranslationResult(status="unsupported", message=reason, attempts=attempts)

        try:
            full_ir, assumptions = apply_defaults(parsed)
            validate_ir(full_ir)
        except (DefaultingError, jsonschema.ValidationError) as exc:
            error = str(exc)
            attempts.append(TranslationAttempt(raw_response=raw, error=error))
            user_message = _retry_message(nl_text, error)
            logger.warning("translate_to_ir: attempt %d validation failed: %s", attempt_num, error)
            continue

        attempts.append(TranslationAttempt(raw_response=raw, error=None))
        logger.info(
            "translate_to_ir: success on attempt %d, sparse_ir=%r, full_ir=%r, assumptions=%r",
            attempt_num,
            parsed,
            full_ir,
            assumptions,
        )
        return TranslationResult(
            status="ok",
            sparse_ir=parsed,
            full_ir=full_ir,
            assumptions=assumptions,
            attempts=attempts,
        )

    last_error = attempts[-1].error if attempts else "no attempts made"
    logger.error("translate_to_ir: exhausted %d retries, last error: %s", max_retries, last_error)
    return TranslationResult(
        status="error",
        message=f"Could not produce a valid strategy after {max_retries} attempts. "
        f"Last error: {last_error}",
        attempts=attempts,
    )


def _retry_message(nl_text: str, error: str) -> str:
    return (
        f"Original request: {nl_text}\n\n"
        f"Your previous JSON response was rejected with this error:\n{error}\n\n"
        "Fix only that problem and respond again with JSON only."
    )
