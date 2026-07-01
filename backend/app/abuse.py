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
