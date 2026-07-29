"""Phase 12A: the LLM cost boundary.

Three things are pinned here, all of which used to be true only by accident:

  * the Anthropic SDK client carries EXPLICIT retry/timeout bounds, so the
    application's `MAX_RETRIES` loop is the only retry layer and one counted
    request is one bounded amount of money and wall-clock;
  * the daily spend budget is claimed atomically, so N concurrent threads
    cannot all pass the cap check before any of them increments; and
  * an identical strategy description is translated once and served from a
    bounded cache thereafter -- WITHOUT weakening any gate. A cache hit still
    passes the per-IP rate limiter, still re-validates its IR, and still
    cannot reach a backtest without an explicit /confirm.

The `_isolate_abuse_protection` autouse fixture (conftest.py) turns the cache
OFF and clears it for the whole suite; every test here that wants the cache
opts back in via env, the same way the rate-limit tests do.
"""

from __future__ import annotations

import json
import sys
import threading

import pytest
from fastapi.testclient import TestClient

from app import abuse, main
from app.translation import service
from app.translation.cache import cache_key, normalize, translation_cache
from app.translation.translator import (
    PROMPT_SCHEMA_VERSION,
    AnthropicLLMClient,
    active_model_name,
)


# `app.main` is REBUILT by importlib.reload in test_docs_exposure.py, which
# replaces both the FastAPI instance and the dependency functions. A module-
# level `from app.main import app` captured before that reload goes stale: the
# old app's routes are keyed on the OLD `get_llm_client`, so an override keyed
# on the new one is silently ignored and the route falls through to the REAL
# Anthropic client. Everything here resolves `main.app` / `main.get_llm_client`
# at call time so the app and the override key always come from the same
# generation of the module.
def _client() -> TestClient:
    return TestClient(main.app)


_SIMPLE_SPARSE_IR = {
    "asset": {"ticker": "SPY"},
    "indicators": [{"id": "rsi14", "type": "RSI"}],
    "entry": {"left": "rsi14", "op": "<", "right": 30},
    "exit": {"left": "rsi14", "op": ">", "right": 70},
}

_NL = "buy SPY when RSI drops below 30, sell when RSI rises above 70"


class CountingLLMClient:
    """Counts model calls. Thread-safe: the concurrency test drives it from
    many threads at once."""

    def __init__(self, responses):
        self._responses = list(responses)
        self._lock = threading.Lock()
        self.calls = 0

    def complete(self, *, system, user):
        with self._lock:
            self.calls += 1
            idx = min(self.calls - 1, len(self._responses) - 1)
        return self._responses[idx]


class RaisingLLMClient:
    def __init__(self, exc):
        self._exc = exc
        self.calls = 0

    def complete(self, *, system, user):
        self.calls += 1
        raise self._exc


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    main.app.dependency_overrides.clear()


def _override_llm(fake):
    main.app.dependency_overrides[main.get_llm_client] = lambda: fake
    return fake


def _translate(nl_text=_NL):
    return _client().post("/translate", json={"nl_text": nl_text})


@pytest.fixture
def cache_on(monkeypatch):
    monkeypatch.setenv("NLSB_TRANSLATION_CACHE_ENABLED", "true")
    translation_cache.clear()
    yield
    translation_cache.clear()


# --- TASK 1: the SDK client carries explicit bounds -------------------------


def test_sdk_client_defaults_to_no_sdk_retries_and_a_60s_timeout(monkeypatch):
    # The whole point of Phase 12A: WITHOUT these, the SDK contributes
    # max_retries=2 and timeout=600s underneath MAX_RETRIES=3.
    monkeypatch.delenv("NLSB_ANTHROPIC_MAX_RETRIES", raising=False)
    monkeypatch.delenv("NLSB_ANTHROPIC_TIMEOUT_SECONDS", raising=False)

    sdk_client = AnthropicLLMClient(api_key="test-key")._get_client()

    # Public attributes on the SDK's BaseClient, not private internals.
    assert sdk_client.max_retries == 0
    assert sdk_client.timeout == 60.0


def test_sdk_client_bounds_are_env_overridable(monkeypatch):
    monkeypatch.setenv("NLSB_ANTHROPIC_MAX_RETRIES", "2")
    monkeypatch.setenv("NLSB_ANTHROPIC_TIMEOUT_SECONDS", "12.5")

    sdk_client = AnthropicLLMClient(api_key="test-key")._get_client()

    assert sdk_client.max_retries == 2
    assert sdk_client.timeout == 12.5


def test_sdk_bounds_are_read_at_construction_not_import(monkeypatch):
    """Each client reads the env when it builds its SDK client, so a restart
    with new values takes effect without a code change."""
    monkeypatch.setenv("NLSB_ANTHROPIC_MAX_RETRIES", "1")
    first = AnthropicLLMClient(api_key="k")._get_client()
    monkeypatch.setenv("NLSB_ANTHROPIC_MAX_RETRIES", "3")
    second = AnthropicLLMClient(api_key="k")._get_client()

    assert (first.max_retries, second.max_retries) == (1, 3)


# --- TASK 2: the spend budget is claimed atomically -------------------------


@pytest.fixture
def preemptive_scheduling():
    """Force the interpreter to switch threads aggressively.

    This fixture is the whole reason the concurrency tests below are worth
    anything. At CPython's default 5ms switch interval the old check()/record()
    race is effectively invisible -- the window between the two calls is a few
    microseconds, so a thread is almost never preempted inside it, and a test
    written without this passes against the BROKEN implementation just as
    happily as against the fixed one. Measured against a reimplementation of
    the old pair: 0/10 runs overshot a cap of 1 at the default interval, 10/10
    overshot it (by 4-16x) at 1e-6. Production hits this window because it
    runs it thousands of times, not because it is wide.
    """
    original = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    yield
    sys.setswitchinterval(original)


def test_concurrent_reserves_let_exactly_one_through_at_cap_one(
    monkeypatch, preemptive_scheduling
):
    """THE race this task exists to close. Handlers are sync `def`, so FastAPI
    runs them in anyio's 40-thread pool: with a separate check() and record(),
    every thread could pass the cap check before any of them incremented."""
    monkeypatch.setenv("NLSB_LLM_DAILY_CAP", "1")
    abuse.spend_breaker.reset()

    n = 16
    ready = threading.Barrier(n)
    granted: list[bool] = []
    granted_lock = threading.Lock()

    def _worker():
        ready.wait()  # maximize the overlap
        ok = abuse.spend_breaker.reserve()
        with granted_lock:
            granted.append(ok)

    threads = [threading.Thread(target=_worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(granted) == 1
    assert abuse.spend_breaker.count == 1


def test_reserve_grants_exactly_cap_units_under_heavy_contention(
    monkeypatch, preemptive_scheduling
):
    """Also pins the increment itself: `self._count += 1` is LOAD/ADD/STORE,
    so concurrent increments could lose one and let an extra request through
    later. Exactly `cap` winners, no more and no fewer."""
    cap = 12
    monkeypatch.setenv("NLSB_LLM_DAILY_CAP", str(cap))
    abuse.spend_breaker.reset()

    n = 48
    ready = threading.Barrier(n)
    granted: list[bool] = []
    granted_lock = threading.Lock()

    def _worker():
        ready.wait()
        ok = abuse.spend_breaker.reserve()
        with granted_lock:
            granted.append(ok)

    threads = [threading.Thread(target=_worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(granted) == cap
    assert abuse.spend_breaker.count == cap


def test_concurrent_translate_requests_call_the_model_exactly_cap_times(
    monkeypatch, preemptive_scheduling
):
    """The same race at the HTTP boundary: N simultaneous /translate requests
    against a cap of 1 must produce exactly one model call."""
    monkeypatch.setenv("NLSB_LLM_DAILY_CAP", "1")
    abuse.spend_breaker.reset()
    fake = _override_llm(CountingLLMClient([json.dumps(_SIMPLE_SPARSE_IR)]))

    n = 8
    ready = threading.Barrier(n)
    statuses: list[int] = []
    statuses_lock = threading.Lock()

    def _worker(i):
        # Distinct text per thread so the cache can never mask the race.
        ready.wait()
        resp = _client().post("/translate", json={"nl_text": f"{_NL} (variant {i})"})
        with statuses_lock:
            statuses.append(resp.status_code)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert fake.calls == 1, "the cap must bound ACTUAL model calls, not just responses"
    assert statuses.count(200) == 1
    assert statuses.count(503) == n - 1


def test_oversized_text_is_rejected_without_consuming_budget(monkeypatch):
    """Ordering: the size cap runs BEFORE the budget is claimed, so a request
    that was always going to be rejected never burns a unit it can't use."""
    monkeypatch.setenv("NLSB_MAX_NL_CHARS", "2000")
    monkeypatch.setenv("NLSB_LLM_DAILY_CAP", "5")
    abuse.spend_breaker.reset()
    fake = _override_llm(CountingLLMClient([json.dumps(_SIMPLE_SPARSE_IR)]))

    resp = _translate("x" * 2001)

    assert resp.status_code == 422
    assert abuse.spend_breaker.count == 0
    assert fake.calls == 0


def test_spend_cap_503_shape_is_unchanged(monkeypatch):
    monkeypatch.setenv("NLSB_LLM_DAILY_CAP", "0")
    abuse.spend_breaker.reset()
    _override_llm(CountingLLMClient([json.dumps(_SIMPLE_SPARSE_IR)]))

    resp = _translate()

    assert resp.status_code == 503
    assert list(resp.json().keys()) == ["detail"]
    assert "daily usage limit" in resp.json()["detail"].lower()


def test_failed_translation_does_not_refund_budget(monkeypatch):
    """A failed call may still have cost real money -- an unspent reservation
    is the safe way to be wrong."""
    monkeypatch.setenv("NLSB_LLM_DAILY_CAP", "5")
    abuse.spend_breaker.reset()
    _override_llm(RaisingLLMClient(RuntimeError("simulated provider outage")))

    assert _translate().status_code == 502
    assert abuse.spend_breaker.count == 1


# --- TASK 3: the translation cache ------------------------------------------


def test_identical_request_twice_calls_the_model_once(cache_on):
    fake = _override_llm(CountingLLMClient([json.dumps(_SIMPLE_SPARSE_IR)]))

    first = _translate()
    second = _translate()

    assert first.status_code == second.status_code == 200
    assert fake.calls == 1
    # Byte-identical at the API boundary, assumptions list included.
    assert first.json() == second.json()
    assert "assumptions" in first.json()


def test_whitespace_and_case_variants_hit_the_same_entry(cache_on):
    fake = _override_llm(CountingLLMClient([json.dumps(_SIMPLE_SPARSE_IR)]))

    assert _translate(_NL).status_code == 200
    assert _translate(f"  {_NL.upper()}  ").status_code == 200
    assert _translate(_NL.replace(" ", "\n  ")).status_code == 200

    assert fake.calls == 1


def test_normalize_does_not_merge_genuinely_different_strategies():
    # Conservative on purpose: punctuation and word order are untouched, so
    # two different strategies can never normalize together.
    assert normalize("Buy  SPY\nwhen RSI < 30") == normalize("buy spy when rsi < 30")
    assert normalize("buy SPY when RSI < 30") != normalize("buy QQQ when RSI < 30")
    assert normalize("sell when RSI > 70") != normalize("sell when RSI > 71")


def test_cache_hit_does_not_consume_spend_budget(cache_on, monkeypatch):
    monkeypatch.setenv("NLSB_LLM_DAILY_CAP", "1")
    abuse.spend_breaker.reset()
    fake = _override_llm(CountingLLMClient([json.dumps(_SIMPLE_SPARSE_IR)]))

    assert _translate().status_code == 200
    assert abuse.spend_breaker.count == 1

    # The budget is now exhausted. A cache hit makes no API call, so it must
    # still succeed rather than 503.
    assert _translate().status_code == 200
    assert abuse.spend_breaker.count == 1
    assert fake.calls == 1


def test_cache_hit_is_still_rate_limited(cache_on, monkeypatch):
    """The cache saves money, not gates. A hit is still a request.

    Deliberately written as "send until the limiter fires" rather than with
    exact counts: `test_docs_exposure.py` rebuilds `app.main` with
    importlib.reload, and each rebuild re-applies the shared limit decorator to
    the same scope, so one request consumes (reloads + 1) units of the
    per-minute budget. Measured at a limit of 6: 6 requests get through with no
    reloads, 3 after one, 2 after two. Asserting a fixed number here would pin
    test-execution ORDER, not behavior.
    """
    monkeypatch.setenv("NLSB_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("NLSB_RATE_LIMIT_LLM_PER_MIN", "30")
    fake = _override_llm(CountingLLMClient([json.dumps(_SIMPLE_SPARSE_IR)]))

    statuses: list[int] = []
    for _ in range(60):
        statuses.append(_translate().status_code)
        if statuses[-1] == 429:
            break

    assert 429 in statuses, "cached traffic must still hit the per-IP limiter"
    # Several requests succeeded before the limiter fired, and exactly one of
    # them reached the model -- so genuine cache hits were rate-limited too.
    assert statuses.count(200) >= 2
    assert fake.calls == 1


def test_a_failing_translation_is_never_cached(cache_on):
    """Only the fully-validated success path is stored. A raising client must
    leave nothing behind, or the failure would be served forever."""
    _override_llm(RaisingLLMClient(RuntimeError("simulated provider outage")))
    assert _translate().status_code == 502

    good = _override_llm(CountingLLMClient([json.dumps(_SIMPLE_SPARSE_IR)]))
    assert _translate().status_code == 200
    assert good.calls == 1  # it really did re-translate


def test_error_and_unsupported_results_are_not_cached(cache_on):
    # Persistent garbage -> the translator's clean "error" path, exhausting
    # MAX_RETRIES. Nothing about that is worth remembering.
    garbage = _override_llm(CountingLLMClient(["not JSON at all"]))
    first = service.translate("some unparseable strategy", llm_client=garbage)
    assert first.status == "error"

    again = CountingLLMClient(["not JSON at all"])
    second = service.translate("some unparseable strategy", llm_client=again)
    assert second.status == "error"
    assert again.calls > 0  # re-translated, not served from cache

    unsupported = CountingLLMClient(
        [json.dumps({"unsupported": True, "reason": "options aren't supported"})]
    )
    service.translate("buy SPY calls", llm_client=unsupported)
    repeat = CountingLLMClient(
        [json.dumps({"unsupported": True, "reason": "options aren't supported"})]
    )
    service.translate("buy SPY calls", llm_client=repeat)
    assert repeat.calls == 1


def test_cache_is_bounded_and_evicts_oldest(cache_on, monkeypatch):
    """Bounded size is a security property: unbounded, anyone could exhaust
    memory with unique strings."""
    monkeypatch.setenv("NLSB_TRANSLATION_CACHE_SIZE", "3")
    fake = _override_llm(CountingLLMClient([json.dumps(_SIMPLE_SPARSE_IR)]))

    for i in range(4):  # size + 1 distinct entries
        assert _translate(f"{_NL} (strategy {i})").status_code == 200

    assert len(translation_cache) == 3
    assert fake.calls == 4

    # Entry 0 was evicted, so it must re-translate; entry 3 is still resident.
    assert _translate(f"{_NL} (strategy 0)").status_code == 200
    assert fake.calls == 5
    assert _translate(f"{_NL} (strategy 3)").status_code == 200
    assert fake.calls == 5


def test_bumping_the_prompt_schema_version_misses_old_entries(cache_on, monkeypatch):
    fake = _override_llm(CountingLLMClient([json.dumps(_SIMPLE_SPARSE_IR)]))
    assert _translate().status_code == 200
    assert fake.calls == 1

    # A prompt or schema change retires every existing entry at once.
    monkeypatch.setattr(service, "PROMPT_SCHEMA_VERSION", PROMPT_SCHEMA_VERSION + 1)
    assert _translate().status_code == 200
    assert fake.calls == 2


def test_changing_the_model_misses_old_entries(cache_on, monkeypatch):
    fake = _override_llm(CountingLLMClient([json.dumps(_SIMPLE_SPARSE_IR)]))
    assert _translate().status_code == 200

    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-some-other-model")
    assert _translate().status_code == 200
    assert fake.calls == 2


def test_cache_disabled_translates_every_time(monkeypatch):
    monkeypatch.setenv("NLSB_TRANSLATION_CACHE_ENABLED", "false")
    fake = _override_llm(CountingLLMClient([json.dumps(_SIMPLE_SPARSE_IR)]))

    assert _translate().status_code == 200
    assert _translate().status_code == 200
    assert fake.calls == 2
    assert len(translation_cache) == 0


def test_a_cached_entry_that_no_longer_validates_is_evicted_not_served(cache_on):
    """The cache is a cost optimization, NEVER a trust boundary. If a stored
    IR stops validating, it is dropped and the request translates fresh --
    the validator, not the cache, decides what a user is asked to confirm."""
    fake = _override_llm(CountingLLMClient([json.dumps(_SIMPLE_SPARSE_IR)]))
    assert _translate().status_code == 200
    assert fake.calls == 1

    # Corrupt the stored entry the way a schema change would.
    key = cache_key(_NL, model=active_model_name(), version=PROMPT_SCHEMA_VERSION)
    poisoned = translation_cache.get(key)
    poisoned.ir["entry"] = {"not": "a valid condition"}
    translation_cache.put(key, poisoned)

    resp = _translate()

    assert resp.status_code == 200
    assert fake.calls == 2, "the invalid entry must be evicted and re-translated"
    assert resp.json()["ir"]["entry"] == {"left": "rsi14", "op": "<", "right": 30}


def test_a_mutated_response_cannot_poison_the_cache(cache_on):
    """Entries are deep-copied in and out: one request mutating the IR it was
    handed must not change what the next request sees."""
    fake = CountingLLMClient([json.dumps(_SIMPLE_SPARSE_IR)])
    first = service.translate(_NL, llm_client=fake)
    first.ir["asset"]["ticker"] = "MUTATED"
    first.assumptions.clear()

    second = service.translate(_NL, llm_client=fake)
    assert fake.calls == 1  # the second was a cache hit

    assert second.ir["asset"]["ticker"] == "SPY"
    assert second.assumptions  # not the emptied list


# --- INVARIANTS: the gate is never bypassed ---------------------------------


def test_cached_translation_still_cannot_reach_a_backtest(cache_on, monkeypatch):
    """INV: a cached translation reaches the user through the IDENTICAL gate
    path as a fresh one. /translate has no code path to the engine -- cache
    hit or miss -- and only an explicit /confirm can run anything."""

    def _explode(*args, **kwargs):
        raise AssertionError("a backtest must never run from /translate")

    monkeypatch.setattr(service, "run_ir_backtest", _explode)
    monkeypatch.setattr(service, "run_robustness", _explode)
    fake = _override_llm(CountingLLMClient([json.dumps(_SIMPLE_SPARSE_IR)]))

    fresh = _translate()
    cached = _translate()

    assert fake.calls == 1  # the second really was a cache hit
    assert fresh.status_code == cached.status_code == 200
    # Identical shape: same keys, same restatement to confirm, same assumptions.
    assert fresh.json() == cached.json()
    # And neither response is a result -- it is still only a proposal.
    assert "verdict" not in cached.json()
    assert cached.json()["restatement"]


def test_cache_hit_carries_no_provider_error_text(cache_on):
    """No raw provider text or stack trace crosses the boundary on either
    path -- pinned for the cached path too."""
    _override_llm(RaisingLLMClient(RuntimeError("secret provider detail 0xDEADBEEF")))
    first = _translate()

    assert first.status_code == 502
    assert "0xDEADBEEF" not in first.text
    assert "Traceback" not in first.text
