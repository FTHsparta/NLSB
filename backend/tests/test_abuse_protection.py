"""Phase 8A: abuse protection & boundary hardening.

Covers the five public-exposure guards without ever sleeping: the rate
limiter is exercised with a low test-configured limit, the spend breaker
with a cap of 1, and the failure boundaries with fake clients that raise or
return degenerate data. The `_isolate_abuse_protection` autouse fixture
(conftest.py) resets the process-global limiter/breaker before each test and
turns both off by default; each test here opts back in via env.
"""

from __future__ import annotations

import json
import logging

import pandas as pd
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import abuse, main
from app.data import market_data
from app.main import app

client = TestClient(app)


_SIMPLE_SPARSE_IR = {
    "asset": {"ticker": "SPY"},
    "indicators": [{"id": "rsi14", "type": "RSI"}],
    "entry": {"left": "rsi14", "op": "<", "right": 30},
    "exit": {"left": "rsi14", "op": ">", "right": 70},
}

_FULL_IR = {
    "asset": {"ticker": "SPY", "asset_class": "equity"},
    "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}],
    "entry": {"left": "rsi14", "op": "<", "right": 30},
    "exit": {"left": "rsi14", "op": ">", "right": 70},
    "position": {"direction": "long", "size": "full"},
    "risk": None,
}


class FakeLLMClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, *, system, user):
        self.calls.append({"system": system, "user": user})
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
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
    app.dependency_overrides.clear()


def _override_llm(responses):
    fake = FakeLLMClient(responses)
    app.dependency_overrides[main.get_llm_client] = lambda: fake
    return fake


def _override_raising_llm(exc):
    fake = RaisingLLMClient(exc)
    app.dependency_overrides[main.get_llm_client] = lambda: fake
    return fake


def _translate(nl_text="buy SPY when RSI < 30, sell when RSI > 70", headers=None):
    return client.post("/translate", json={"nl_text": nl_text}, headers=headers)


def _confirm(ticker="SPY", ir=None):
    return client.post(
        "/confirm",
        json={"ir": ir or _FULL_IR, "assumptions": [], "ticker": ticker, "start": "2015-01-01"},
    )


# --- TASK 1: per-IP rate limiting -------------------------------------------


def test_llm_route_returns_429_json_when_per_minute_limit_exceeded(monkeypatch):
    monkeypatch.setenv("NLSB_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("NLSB_RATE_LIMIT_LLM_PER_MIN", "2")
    _override_llm([json.dumps(_SIMPLE_SPARSE_IR)])

    assert _translate().status_code == 200
    assert _translate().status_code == 200
    third = _translate()
    assert third.status_code == 429
    body = third.json()
    assert list(body.keys()) == ["detail"]  # exactly {"detail": <plain english>}
    assert isinstance(body["detail"], str) and body["detail"]


def test_translate_and_correct_share_one_budget(monkeypatch):
    monkeypatch.setenv("NLSB_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("NLSB_RATE_LIMIT_LLM_PER_MIN", "2")
    _override_llm([json.dumps(_SIMPLE_SPARSE_IR)])

    # Two translates exhaust the shared budget; a correct is then rejected --
    # proving /translate and /correct draw from ONE per-IP bucket.
    assert _translate().status_code == 200
    assert _translate().status_code == 200
    correct = client.post(
        "/correct",
        json={"original_nl": "buy SPY when oversold", "prior_ir": _SIMPLE_SPARSE_IR, "correction_text": "use RSI(14)"},
    )
    assert correct.status_code == 429


def test_confirm_has_its_own_limit(monkeypatch):
    monkeypatch.setenv("NLSB_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("NLSB_RATE_LIMIT_CONFIRM_PER_MIN", "2")
    app.dependency_overrides[main.get_price_fetcher] = _fake_price_fetcher

    assert _confirm().status_code == 200
    assert _confirm().status_code == 200
    assert _confirm().status_code == 429


# --- TASK 1b: proxy-aware rate-limit key ------------------------------------
#
# Behind Railway's edge proxy the TCP peer is the PROXY for every visitor, so
# keying on it puts all traffic in one bucket and real users block each other.
# `client_identity` keys on the leftmost X-Forwarded-For entry instead -- but
# only when NLSB_TRUST_PROXY_HEADERS is on, so local dev is unchanged.


def _fake_request(headers=None, client=("10.0.0.1", 51234)):
    """A minimal ASGI scope is enough: the key function only reads headers and
    request.client, never a body."""
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/translate",
            "headers": [
                (k.lower().encode("latin-1"), v.encode("latin-1"))
                for k, v in (headers or {}).items()
            ],
            "client": client,
        }
    )


def test_key_func_uses_leftmost_forwarded_entry_when_trusted(monkeypatch):
    monkeypatch.setenv("NLSB_TRUST_PROXY_HEADERS", "true")
    req = _fake_request({"X-Forwarded-For": "203.0.113.7, 100.64.0.2, 100.64.0.9"})
    assert abuse.client_identity(req) == "203.0.113.7"


def test_key_func_uses_direct_address_when_header_absent(monkeypatch):
    monkeypatch.setenv("NLSB_TRUST_PROXY_HEADERS", "true")
    assert abuse.client_identity(_fake_request()) == "10.0.0.1"


def test_key_func_ignores_forwarded_header_when_trust_disabled(monkeypatch):
    # The gate: with trust off the header is inert, even when present. This is
    # what keeps a directly-exposed process un-spoofable.
    monkeypatch.setenv("NLSB_TRUST_PROXY_HEADERS", "false")
    req = _fake_request({"X-Forwarded-For": "203.0.113.7"})
    assert abuse.client_identity(req) == "10.0.0.1"


def test_key_func_default_is_trust_disabled(monkeypatch):
    # Unset (not just "false") must behave identically to today.
    monkeypatch.delenv("NLSB_TRUST_PROXY_HEADERS", raising=False)
    req = _fake_request({"X-Forwarded-For": "203.0.113.7"})
    assert abuse.client_identity(req) == "10.0.0.1"


@pytest.mark.parametrize(
    "header_value, expected",
    [
        ("  203.0.113.7  ", "203.0.113.7"),  # surrounding whitespace
        ("203.0.113.7", "203.0.113.7"),  # single value, no chain
        ("  203.0.113.7 ,100.64.0.2 ", "203.0.113.7"),  # whitespace in a chain
        ("", "10.0.0.1"),  # empty header -> direct address
        (",,", "10.0.0.1"),  # malformed: empty leftmost -> direct address
        ("   ", "10.0.0.1"),  # whitespace-only -> direct address
    ],
)
def test_key_func_handles_odd_header_values_without_raising(monkeypatch, header_value, expected):
    monkeypatch.setenv("NLSB_TRUST_PROXY_HEADERS", "true")
    req = _fake_request({"X-Forwarded-For": header_value})
    assert abuse.client_identity(req) == expected


def test_key_func_falls_back_to_sentinel_rather_than_raising(monkeypatch):
    # Nothing resolvable at all: the limiter must degrade to a shared bucket,
    # never blow up in the key function (which runs before the route).
    monkeypatch.setenv("NLSB_TRUST_PROXY_HEADERS", "true")
    monkeypatch.setattr(abuse, "get_remote_address", lambda request: "")
    assert abuse.client_identity(_fake_request(client=None)) == abuse.UNKNOWN_CLIENT


def test_distinct_forwarded_ips_get_separate_rate_limit_buckets(monkeypatch):
    # THE regression this exists to prevent: one visitor exhausting the limit
    # must not lock out a different visitor arriving through the same proxy.
    monkeypatch.setenv("NLSB_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("NLSB_TRUST_PROXY_HEADERS", "true")
    monkeypatch.setenv("NLSB_RATE_LIMIT_LLM_PER_MIN", "2")
    _override_llm([json.dumps(_SIMPLE_SPARSE_IR)])

    visitor_a = {"X-Forwarded-For": "203.0.113.7, 100.64.0.2"}
    visitor_b = {"X-Forwarded-For": "198.51.100.23, 100.64.0.2"}

    assert _translate(headers=visitor_a).status_code == 200
    assert _translate(headers=visitor_a).status_code == 200
    assert _translate(headers=visitor_a).status_code == 429  # A is exhausted

    # B shares the proxy but not the bucket.
    assert _translate(headers=visitor_b).status_code == 200
    assert _translate(headers=visitor_b).status_code == 200


def test_distinct_forwarded_ips_share_one_bucket_when_trust_disabled(monkeypatch):
    # The pre-fix behavior, pinned: with the gate off the header is ignored, so
    # both "visitors" collapse into the single TestClient-peer bucket.
    monkeypatch.setenv("NLSB_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("NLSB_TRUST_PROXY_HEADERS", "false")
    monkeypatch.setenv("NLSB_RATE_LIMIT_LLM_PER_MIN", "2")
    _override_llm([json.dumps(_SIMPLE_SPARSE_IR)])

    assert _translate(headers={"X-Forwarded-For": "203.0.113.7"}).status_code == 200
    assert _translate(headers={"X-Forwarded-For": "198.51.100.23"}).status_code == 200
    assert _translate(headers={"X-Forwarded-For": "192.0.2.44"}).status_code == 429


# --- TASK 2: daily spend circuit breaker ------------------------------------


def test_spend_breaker_short_circuits_before_the_llm_is_called(monkeypatch):
    monkeypatch.setenv("NLSB_LLM_DAILY_CAP", "1")
    fake = _override_llm([json.dumps(_SIMPLE_SPARSE_IR)])

    first = _translate()
    assert first.status_code == 200

    second = _translate()
    assert second.status_code == 503
    assert "daily usage limit" in second.json()["detail"].lower()

    # The breaker stopped the second request BEFORE reaching the client: the
    # fake recorded exactly one call across both requests.
    assert len(fake.calls) == 1


# --- TASK 3: input caps & validation ----------------------------------------


def test_oversized_strategy_text_is_rejected_before_the_llm(monkeypatch):
    monkeypatch.setenv("NLSB_MAX_NL_CHARS", "2000")
    fake = _override_llm([json.dumps(_SIMPLE_SPARSE_IR)])

    resp = _translate("x" * 2001)
    assert resp.status_code == 422
    assert "too long" in resp.json()["detail"].lower()
    assert len(fake.calls) == 0  # never reached the model


def test_malformed_ticker_is_rejected_before_yfinance():
    calls = {"n": 0}

    def _spy_fetcher():
        def _fetch(ticker, start, end=None, **kwargs):
            calls["n"] += 1
            raise AssertionError("yfinance must not be called for a malformed ticker")

        return _fetch

    app.dependency_overrides[main.get_price_fetcher] = _spy_fetcher

    resp = _confirm(ticker="NOT A TICKER!")
    assert resp.status_code == 422
    assert "ticker" in resp.json()["detail"].lower()
    assert calls["n"] == 0


# --- TASK 4: external-call failure boundaries -------------------------------


def test_llm_transport_error_becomes_502_not_500(monkeypatch):
    _override_raising_llm(RuntimeError("simulated Anthropic outage"))

    resp = _translate()
    assert resp.status_code == 502
    assert isinstance(resp.json()["detail"], str)
    # The raw exception text never crosses the boundary.
    assert "simulated Anthropic outage" not in resp.text


def test_empty_price_frame_becomes_clean_error_not_keyerror(monkeypatch):
    # Use the REAL fetcher (default dependency), but make yfinance hand back an
    # empty frame -- the boundary must catch it as a clean error, never let a
    # KeyError surface from deep in the engine.
    monkeypatch.setattr(market_data.yf, "download", lambda *a, **k: pd.DataFrame())

    resp = _confirm(ticker="BOGUS")
    assert resp.status_code == 422
    assert "BOGUS" in resp.json()["detail"]
    assert "Traceback" not in resp.text and "KeyError" not in resp.text


def test_global_handler_returns_generic_500_with_no_traceback():
    # A tiny app reusing the production handler, with a route that raises an
    # uncaught error -- proving the final net hides the traceback.
    test_app = FastAPI()
    test_app.add_exception_handler(Exception, main.unhandled_exception_handler)

    @test_app.get("/boom")
    def _boom():
        raise RuntimeError("secret internal detail 0xDEADBEEF")

    boom_client = TestClient(test_app, raise_server_exceptions=False)
    resp = boom_client.get("/boom")

    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("application/json")
    assert "secret internal detail" not in resp.text
    assert "Traceback" not in resp.text
    assert "0xDEADBEEF" not in resp.text
    assert isinstance(resp.json()["detail"], str)


# --- TASK 5: structured request logging -------------------------------------


def test_request_logging_middleware_emits_a_record(caplog):
    with caplog.at_level(logging.INFO, logger="app.request"):
        resp = client.get("/health")
    assert resp.status_code == 200
    records = [r for r in caplog.records if r.name == "app.request"]
    assert any("/health" in r.getMessage() for r in records)


# --- shared price fetcher (mirrors test_api_routes.py) ----------------------


def _fake_price_fetcher():
    import numpy as np

    n = 200
    block = np.concatenate([-np.ones(20), np.ones(20)])
    reps = int(np.ceil((n - 1) / len(block)))
    deltas = np.tile(block, reps)[: n - 1]
    close = 100 + np.concatenate([[0], np.cumsum(deltas)])
    idx = pd.date_range("2015-01-01", periods=n, freq="D")
    close = pd.Series(close, index=idx, dtype=float)
    frame = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close})

    def _fetch(ticker, start, end=None, **kwargs):
        return frame

    return _fetch
