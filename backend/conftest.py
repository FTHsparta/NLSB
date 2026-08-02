"""Shared test fixtures for the backend suite.

Phase 8A adds process-global abuse protection (a per-IP rate limiter and a
daily spend breaker) whose state persists across requests -- and therefore
across test cases -- and which, at their production defaults, would throttle
the suite's own many same-IP requests. This autouse fixture gives every test
a clean, protection-off baseline: the dedicated abuse-protection tests opt
back in explicitly (re-enabling the limiter / lowering the cap via env). It
touches no assertion; it only isolates shared state.
"""

from __future__ import annotations

import pytest

from app import abuse
from app.data.market_data import price_cache
from app.translation import service
from app.translation.cache import translation_cache


@pytest.fixture(autouse=True)
def _forbid_real_llm_calls(request, monkeypatch):
    """Fail loudly rather than spend real money.

    `backend/.env` holds a working ANTHROPIC_API_KEY and `app.main` calls
    `load_dotenv()` at import, so any test whose fake-client override fails to
    apply does not error -- it quietly calls the REAL API and passes. That is
    exactly what happened once: `test_docs_exposure.py` rebuilds `app.main`
    with `importlib.reload`, which replaces the dependency FUNCTIONS, so a
    later test file overriding `main.get_llm_client` was keying on a function
    the live app's routes no longer referenced. The override was ignored in
    silence and the suite billed a real account.

    This guard makes that failure mode impossible to miss: the only way to
    reach the real client is the `live` marker, which CI deselects.
    """
    if request.node.get_closest_marker("live"):
        return

    def _forbidden():
        raise AssertionError(
            "This test reached the REAL Anthropic client. A dependency override "
            "is not being applied -- check that the test resolves `main.app` and "
            "`main.get_llm_client` from the SAME generation of the module "
            "(test_docs_exposure.py reloads it)."
        )

    monkeypatch.setattr(service, "_default_llm_client", _forbidden)


@pytest.fixture(autouse=True)
def _isolate_abuse_protection(monkeypatch):
    # Off by default for the suite; opt-in tests override these via setenv.
    monkeypatch.setenv("NLSB_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("NLSB_LLM_DAILY_CAP", "1000000")
    # Pinned (not just left to its default) so a developer with this set in
    # their shell can't silently change which bucket a test request lands in.
    monkeypatch.setenv("NLSB_TRUST_PROXY_HEADERS", "false")
    # Phase 12A: same treatment as the limiter -- a process-global cache that
    # is ON in production would otherwise make one test's translation answer
    # another test's identical request. Cache tests opt back in via setenv.
    monkeypatch.setenv("NLSB_TRANSLATION_CACHE_ENABLED", "false")
    # Phase 12B: same reasoning for the price cache -- one test's patched
    # yf.download must never answer another test's fetch. Cache tests opt in.
    monkeypatch.setenv("NLSB_PRICE_CACHE_ENABLED", "false")
    # Phase 12E: event recording writes to disk. Off by default so no test
    # creates a database as a side effect; test_events.py opts back in and
    # points the store at a tmp_path. Also keeps the read routes 404 (they
    # fail closed on an unset token) unless a test sets one deliberately.
    monkeypatch.setenv("NLSB_EVENTS_ENABLED", "false")
    monkeypatch.delenv("NLSB_EVENTS_TOKEN", raising=False)

    # Clear process-global counters so no test inherits another's usage.
    abuse.spend_breaker.reset()
    abuse.reset_rate_limiter()
    translation_cache.clear()
    price_cache.clear()
    yield
    abuse.spend_breaker.reset()
    abuse.reset_rate_limiter()
    translation_cache.clear()
    price_cache.clear()
