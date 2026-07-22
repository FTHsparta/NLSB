"""HTTP-boundary tests for /translate, /correct, /confirm.

CONTRACT 1: neither /translate nor /correct can reach the backtester.
CONTRACT 2: /confirm is the ONLY route that yields a robustness result.

Both are asserted the same way Phase 3's own tests assert the Python-level
guarantee (`test_translation_service.py::test_translate_returns_ir_and_restatement_without_running_backtest`):
monkeypatch the actual run function and fail loudly if it's ever called on
the routes that must not reach it.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app

client = TestClient(app)


class FakeLLMClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, *, system, user):
        self.calls.append({"system": system, "user": user})
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[idx]


def _oscillating_close(n: int = 200) -> pd.Series:
    block = np.concatenate([-np.ones(20), np.ones(20)])
    reps = int(np.ceil((n - 1) / len(block)))
    deltas = np.tile(block, reps)[: n - 1]
    close = 100 + np.concatenate([[0], np.cumsum(deltas)])
    idx = pd.date_range("2015-01-01", periods=n, freq="D")
    return pd.Series(close, index=idx, dtype=float)


def _price_data(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close})


_SIMPLE_SPARSE_IR = {
    "asset": {"ticker": "SPY"},
    "indicators": [{"id": "rsi14", "type": "RSI"}],
    "entry": {"left": "rsi14", "op": "<", "right": 30},
    "exit": {"left": "rsi14", "op": ">", "right": 70},
}


def _fake_price_fetcher():
    close = _oscillating_close()
    frame = _price_data(close)

    def _fetch(ticker, start, end=None, **kwargs):
        return frame

    return _fetch


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _override_llm(responses):
    fake = FakeLLMClient(responses)
    app.dependency_overrides[main.get_llm_client] = lambda: fake
    return fake


def _override_price_fetcher():
    app.dependency_overrides[main.get_price_fetcher] = _fake_price_fetcher


# --- CONTRACT 1: /translate and /correct never reach the backtester ---


def test_translate_route_never_calls_run_ir_backtest(monkeypatch):
    def _spy(*args, **kwargs):
        raise AssertionError("run_ir_backtest must not be called from /translate")

    monkeypatch.setattr(main.service, "run_ir_backtest", _spy)
    _override_llm([json.dumps(_SIMPLE_SPARSE_IR)])

    resp = client.post("/translate", json={"nl_text": "buy SPY when RSI < 30, sell when RSI > 70"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["ir"] is not None
    assert "SPY" in body["restatement"]


def test_translate_route_never_calls_run_robustness(monkeypatch):
    def _spy(*args, **kwargs):
        raise AssertionError("run_robustness must not be called from /translate")

    monkeypatch.setattr(main.service, "run_robustness", _spy)
    _override_llm([json.dumps(_SIMPLE_SPARSE_IR)])

    resp = client.post("/translate", json={"nl_text": "buy SPY when RSI < 30, sell when RSI > 70"})

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_correct_route_never_calls_run_robustness(monkeypatch):
    def _spy(*args, **kwargs):
        raise AssertionError("run_robustness must not be called from /correct")

    monkeypatch.setattr(main.service, "run_robustness", _spy)
    _override_llm([json.dumps(_SIMPLE_SPARSE_IR)])

    resp = client.post(
        "/correct",
        json={
            "original_nl": "buy SPY when oversold",
            "prior_ir": {"asset": {"ticker": "SPY"}, "entry": {"left": "close", "op": "<", "right": 30}},
            "correction_text": "use RSI(14) below 30, not raw close",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_translate_route_propagates_unsupported_without_touching_backtester(monkeypatch):
    def _spy(*args, **kwargs):
        raise AssertionError("must not be called for an unsupported request")

    monkeypatch.setattr(main.service, "run_robustness", _spy)
    monkeypatch.setattr(main.service, "run_ir_backtest", _spy)
    _override_llm([json.dumps({"unsupported": True, "reason": "Options aren't supported in v1."})])

    resp = client.post("/translate", json={"nl_text": "buy SPY call options when RSI < 30"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unsupported"
    assert body["ir"] is None


# --- CONTRACT 2: /confirm is the ONLY route that yields a robustness result ---


def test_confirm_route_is_the_only_path_to_a_robustness_result():
    _override_price_fetcher()
    full_ir = {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        "exit": {"left": "rsi14", "op": ">", "right": 70},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }

    resp = client.post(
        "/confirm",
        json={"ir": full_ir, "assumptions": [], "ticker": "SPY", "start": "2015-01-01"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"kind", "no_exit", "sensitivity", "walk_forward", "deflated_sharpe", "regime", "verdict"}
    assert body["kind"] == "full"
    assert body["verdict"] is not None


def test_confirm_route_no_exit_assumption_short_circuits_to_buy_and_hold():
    _override_price_fetcher()
    full_ir = {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        "exit": {"left": "close", "op": "<", "right": "close"},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }
    no_exit_assumption = {
        "field": "exit",
        "value": {"left": "close", "op": "<", "right": "close"},
        "reason": "no exit condition stated; approximates buy-and-hold",
        "severity": "warning",
    }

    resp = client.post(
        "/confirm",
        json={"ir": full_ir, "assumptions": [no_exit_assumption], "ticker": "SPY", "start": "2015-01-01"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "no_exit"
    assert body["no_exit"] is not None
    assert body["verdict"] is None


def test_translate_route_rejects_stop_bearing_ir_as_unsupported(monkeypatch):
    """Pre-launch honesty fix: a schema-valid IR carrying a stop-loss is
    rejected deterministically (the engine doesn't simulate stops), reusing
    the existing unsupported surface — the user never sees a gate for it."""

    def _spy(*args, **kwargs):
        raise AssertionError("must not be called for a stop-bearing request")

    monkeypatch.setattr(main.service, "run_robustness", _spy)
    monkeypatch.setattr(main.service, "run_ir_backtest", _spy)
    stop_bearing = {**_SIMPLE_SPARSE_IR, "risk": {"stop_loss_pct": 0.05}}
    _override_llm([json.dumps(stop_bearing)])

    resp = client.post("/translate", json={"nl_text": "buy SPY when RSI < 30, with a 5% stop loss"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unsupported"
    assert body["ir"] is None
    assert body["restatement"] is None
    assert "stop-loss" in body["message"]


def test_confirm_route_rejects_stop_bearing_ir_with_400():
    """Same guard at the only run path: a stop-bearing IR POSTed straight to
    /confirm (bypassing translate) gets a 400 with the honest reason, never
    results that silently ignore the stop."""
    _override_price_fetcher()
    full_ir = {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        "exit": {"left": "rsi14", "op": ">", "right": 70},
        "position": {"direction": "long", "size": "full"},
        "risk": {"stop_loss_pct": 0.05, "take_profit_pct": None},
    }

    resp = client.post(
        "/confirm",
        json={"ir": full_ir, "assumptions": [], "ticker": "SPY", "start": "2015-01-01"},
    )

    assert resp.status_code == 400
    assert "stop-loss" in resp.json()["detail"]


def test_confirm_route_rejects_invalid_ir():
    _override_price_fetcher()
    resp = client.post(
        "/confirm",
        json={"ir": {"not": "a valid ir"}, "assumptions": [], "ticker": "SPY", "start": "2015-01-01"},
    )
    assert resp.status_code == 400


def test_translate_and_correct_routes_have_no_dependency_on_price_fetcher(monkeypatch):
    """A route that never needs price data structurally cannot have run
    anything that requires it -- confirms /translate doesn't even declare
    the price-fetcher dependency."""
    import inspect

    sig = inspect.signature(main.translate_route)
    assert "price_fetcher" not in sig.parameters
    sig = inspect.signature(main.correct_route)
    assert "price_fetcher" not in sig.parameters
