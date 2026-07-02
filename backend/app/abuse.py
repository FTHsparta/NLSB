"""Abuse protection & boundary hardening for the public HTTP surface.

This module is a *gate*, not business logic. It holds the three things that
must run before any LLM-calling route reaches the Anthropic client -- the
per-IP rate limiter, the daily spend circuit breaker, and the input size
cap -- plus ticker validation for the confirm path and one-time logging
setup. `app.main` composes these in front of the existing route handlers;
none of it changes what the LLM emits or how the IR is validated.

Security boundary (unchanged): the LLM still emits only validated IR JSON,
and nothing here or downstream ever executes model-emitted code.

Every configurable knob reads its environment variable *at call time* (not
at import) so tests can set a low limit / small cap without reimporting the
app, and so `.env` changes take effect on restart without code edits.
"""

from __future__ import annotations

import logging
import math
import os
import re
from datetime import datetime, timezone

from fastapi import HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger("app.abuse")


# --- Rate limiting (per client IP) ------------------------------------------

# One process-wide limiter with in-memory ("memory://") fixed-window storage.
# In-memory is acceptable for a single-process V1; a multi-process deploy
# would need a shared store (e.g. Redis) for the counts to be global.
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")


def rate_limiting_enabled() -> bool:
    return os.environ.get("NLSB_RATE_LIMIT_ENABLED", "true").lower() == "true"


def _rate_limit_exempt() -> bool:
    """slowapi `exempt_when`: skip the limit entirely when disabled. Lets the
    test suite (and a local dev run) turn rate limiting off without removing
    the decorators that prove the gate exists in production."""
    return not rate_limiting_enabled()


def llm_rate_limit_value() -> str:
    """Shared budget for the two LLM-calling routes (/translate + /correct)."""
    per_min = os.environ.get("NLSB_RATE_LIMIT_LLM_PER_MIN", "10")
    per_day = os.environ.get("NLSB_RATE_LIMIT_LLM_PER_DAY", "60")
    return f"{per_min}/minute;{per_day}/day"


def confirm_rate_limit_value() -> str:
    per_min = os.environ.get("NLSB_RATE_LIMIT_CONFIRM_PER_MIN", "20")
    return f"{per_min}/minute"


# A single shared_limit object applied to BOTH /translate and /correct makes
# them draw from ONE budget per IP (scope="llm"), exactly as specified.
llm_rate_limit = limiter.shared_limit(
    llm_rate_limit_value, scope="llm", exempt_when=_rate_limit_exempt
)
confirm_rate_limit = limiter.limit(confirm_rate_limit_value, exempt_when=_rate_limit_exempt)


def reset_rate_limiter() -> None:
    """Clear all counters. For tests only -- the limiter's storage is
    process-global and would otherwise leak counts between test cases."""
    try:
        limiter.reset()
    except Exception:  # pragma: no cover - storage without reset support
        logger.warning("rate limiter storage does not support reset()")


# --- Daily LLM spend circuit breaker ----------------------------------------


class SpendBreaker:
    """Process-level counter of LLM-calling requests per UTC day, with a hard
    cap. In-memory and single-process only (a V1 limitation): the count is not
    shared across workers and resets on restart. Each counted request may make
    up to `MAX_RETRIES` underlying model calls; this counts *requests that are
    allowed to call the model*, reserved before the client is invoked.
    """

    def __init__(self) -> None:
        self._day: object = None
        self._count = 0

    @staticmethod
    def _cap() -> int:
        return int(os.environ.get("NLSB_LLM_DAILY_CAP", "200"))

    def _roll_day(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self._day:
            self._day = today
            self._count = 0

    def check(self) -> None:
        """Raise 503 if today's cap is already reached. Does NOT mutate the
        counter -- call `record()` once the request has cleared the other
        gates and is about to spend."""
        self._roll_day()
        if self._count >= self._cap():
            logger.warning("daily LLM spend cap reached (%d); short-circuiting", self._cap())
            raise HTTPException(
                status_code=503,
                detail="The service has hit its daily usage limit — try again tomorrow.",
            )

    def record(self) -> None:
        self._roll_day()
        self._count += 1

    def reset(self) -> None:
        """For tests only: clear the process-global counter between cases."""
        self._day = None
        self._count = 0

    @property
    def count(self) -> int:
        self._roll_day()
        return self._count


spend_breaker = SpendBreaker()


# --- Input caps & validation ------------------------------------------------


def max_nl_chars() -> int:
    return int(os.environ.get("NLSB_MAX_NL_CHARS", "2000"))


def enforce_text_size(*texts: str) -> None:
    """Reject oversized free-text before the LLM is called (422). Guards each
    provided NL field independently."""
    cap = max_nl_chars()
    for text in texts:
        if text is not None and len(text) > cap:
            logger.warning("rejected oversized input (%d chars > cap %d)", len(text), cap)
            raise HTTPException(
                status_code=422,
                detail=f"Your strategy description is too long ({len(text)} characters). "
                f"Please shorten it to at most {cap} characters.",
            )


# Conservative: 1-10 chars, uppercase letters / digits / dot / hyphen. Covers
# real symbols (SPY, BRK.B, RDS-A) while rejecting anything that could be an
# injection or a wildcard fed to yfinance.
_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


def enforce_ticker(ticker: str) -> None:
    if not isinstance(ticker, str) or not _TICKER_RE.match(ticker):
        logger.warning("rejected malformed ticker %r", ticker)
        raise HTTPException(
            status_code=422,
            detail=f"{ticker!r} is not a valid ticker symbol. Use 1–10 uppercase "
            "letters, digits, '.', or '-' (e.g. SPY, BRK.B).",
        )


# --- Request body size cap --------------------------------------------------


def max_body_bytes() -> int:
    return int(os.environ.get("NLSB_MAX_BODY_BYTES", "65536"))


def body_length_exceeds_cap(content_length: str | None) -> bool:
    """True when a declared Content-Length exceeds the cap. Absent/malformed
    headers return False (the IR complexity cap below is the structural
    backstop for a body that arrives without a declared length)."""
    if not content_length:
        return False
    try:
        return int(content_length) > max_body_bytes()
    except (TypeError, ValueError):
        return False


# --- IR structural sanitization (pre-validation) ----------------------------
#
# `/confirm` takes a client-supplied IR and schema-validates it, but the
# recursive schema validator (and the robustness engine downstream) trust
# two things the JSON layer does not guarantee:
#   * bounded nesting -- a deeply nested condition tree (~200 `all_of`
#     levels) blows Python's recursion limit and turns into a
#     RecursionError-driven 500 BEFORE the schema can reject it; and
#   * finite numbers -- a lenient client can send NaN/Infinity (json.loads
#     accepts them), which jsonschema treats as valid numbers but which
#     crash later as `int(nan)` inside the sensitivity grid.
# This single iterative pass (its own traversal can never recurse) rejects an
# over-deep, over-large, or non-finite IR with a clean 422 before validation
# or any engine work runs.


def max_ir_depth() -> int:
    return int(os.environ.get("NLSB_MAX_IR_DEPTH", "40"))


def max_ir_nodes() -> int:
    return int(os.environ.get("NLSB_MAX_IR_NODES", "2000"))


def enforce_ir_complexity(ir: object) -> None:
    """Reject an IR whose nesting depth or node count exceeds the cap, or that
    contains a non-finite number, BEFORE the recursive schema validator sees
    it. Iterative by construction so the guard itself cannot raise
    RecursionError on hostile input."""
    depth_cap = max_ir_depth()
    node_cap = max_ir_nodes()
    nodes = 0
    stack: list[tuple[object, int]] = [(ir, 1)]
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if depth > depth_cap:
            logger.warning("rejected over-deep IR (depth > %d)", depth_cap)
            raise HTTPException(
                status_code=422,
                detail="This strategy's entry/exit logic is nested too deeply. "
                "Please simplify it.",
            )
        if nodes > node_cap:
            logger.warning("rejected over-large IR (nodes > %d)", node_cap)
            raise HTTPException(
                status_code=422,
                detail="This strategy has too many elements to process. Please simplify it.",
            )
        # bool is a subclass of int but never float; only genuine floats can be
        # NaN/Infinity, so this rejects exactly the non-finite numeric case.
        if isinstance(node, float) and not math.isfinite(node):
            logger.warning("rejected non-finite number in IR (%r)", node)
            raise HTTPException(
                status_code=422,
                detail="Strategy contains a non-finite number (NaN or Infinity), "
                "which isn't a valid value.",
            )
        if isinstance(node, dict):
            for value in node.values():
                stack.append((value, depth + 1))
        elif isinstance(node, list):
            for value in node:
                stack.append((value, depth + 1))


# --- Logging setup ----------------------------------------------------------

_LOGGING_CONFIGURED = False


def configure_logging() -> None:
    """Configure stdlib logging once at startup. Never logs secrets. Idempotent
    so repeated imports (e.g. under the test runner) don't stack handlers."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return
    level_name = os.environ.get("NLSB_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _LOGGING_CONFIGURED = True
