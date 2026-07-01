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


@pytest.fixture(autouse=True)
def _isolate_abuse_protection(monkeypatch):
    # Off by default for the suite; opt-in tests override these via setenv.
    monkeypatch.setenv("NLSB_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("NLSB_LLM_DAILY_CAP", "1000000")

    # Clear process-global counters so no test inherits another's usage.
    abuse.spend_breaker.reset()
    abuse.reset_rate_limiter()
    yield
    abuse.spend_breaker.reset()
    abuse.reset_rate_limiter()
