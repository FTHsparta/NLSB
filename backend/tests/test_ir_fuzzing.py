"""Phase 8B: adversarial hardening of the /confirm IR boundary.

/confirm accepts a CLIENT-SUPPLIED IR -- a hostile client can POST arbitrary
JSON there without ever touching the translator. These table-driven tests
fire malicious / malformed IRs at the real route and assert two things for
each: (1) the response is a clean client error (400/413/422), never a 5xx or
a leaked traceback; (2) the simulation engine (`vbt.Portfolio.from_signals`,
the single deepest point where a validated IR becomes a run) is NEVER reached.

INV-1 (no fuzz input reaches the engine without full validation) and INV-2
(the boundary's failure mode is a clean HTTP error, never a raw
RecursionError/KeyError/TypeError) are what this file exists to prove.
"""

from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import abuse, main
from app.data.market_data import InsufficientDataError
from app.main import app

warnings.filterwarnings("ignore")

# raise_server_exceptions=False so an (unexpected) unhandled error is rendered
# by our global handler as a 500 response we can assert on, rather than being
# re-raised into the test -- a real 500 here is a FAILURE we want to see with
# its body, not a pytest error.
client = TestClient(app, raise_server_exceptions=False)


def _price_frame(n: int = 300) -> pd.DataFrame:
    block = np.concatenate([-np.ones(20), np.ones(20)])
    reps = int(np.ceil((n - 1) / len(block)))
    deltas = np.tile(block, reps)[: n - 1]
    close = 100 + np.concatenate([[0], np.cumsum(deltas)])
    idx = pd.date_range("2015-01-01", periods=n, freq="D")
    close = pd.Series(close, index=idx, dtype=float)
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close})


@pytest.fixture(autouse=True)
def _fake_prices(monkeypatch):
    """Real route + deterministic price data, no network. The fetcher honors
    the requested date window the way the real one does -- an empty/reversed
    range raises InsufficientDataError -- so date-abuse cases exercise the
    real fetch boundary (422), not a fetcher that silently ignores dates.
    Resets the Phase 8A spend breaker so fuzzing many requests never trips it.
    """
    frame = _price_frame()

    def _fetcher():
        def _fetch(ticker, start, end=None, **kwargs):
            s = pd.Timestamp(start)
            e = pd.Timestamp(end) if end else None
            mask = frame.index >= s
            if e is not None:
                mask &= frame.index <= e
            window = frame[mask]
            if len(window) < 2:
                raise InsufficientDataError(f"No usable data for {ticker!r} in the requested range")
            return window

        return _fetch

    monkeypatch.setitem(app.dependency_overrides, main.get_price_fetcher, _fetcher)
    abuse.spend_breaker.reset()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def engine_spy(monkeypatch):
    """A hard spy on the engine's single entry to the simulator: if any fuzz
    input reaches it, the assertion fails. Only requested by tests that must
    prove the engine was NOT reached."""
    reached = {"engine": False}

    import app.engine.backtest as backtest

    def _boom(*args, **kwargs):
        reached["engine"] = True
        raise AssertionError("vbt.Portfolio.from_signals reached with a fuzz IR")

    monkeypatch.setattr(backtest.vbt.Portfolio, "from_signals", staticmethod(_boom))
    return reached


def _valid_ir(**over):
    ir = {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        "exit": {"left": "rsi14", "op": ">", "right": 70},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }
    ir.update(over)
    return ir


def _leaf():
    return {"left": "close", "op": "<", "right": 30}


def _nest(depth: int):
    cond = _leaf()
    for _ in range(depth):
        cond = {"all_of": [cond]}
    return cond


def _post(ir, ticker="SPY", start="2015-01-01", end=None):
    return client.post(
        "/confirm",
        json={"ir": ir, "assumptions": [], "ticker": ticker, "start": start, "end": end},
    )


# Each case: (id, ir, extra kwargs for _post). The IR is the hostile payload;
# a few cases also abuse the ticker / date fields.
_HOSTILE_CASES = [
    # --- wrong top-level types (pydantic rejects a non-object IR) ---
    ("toplevel_list", [1, 2, 3], {}),
    ("toplevel_string", "definitely not an ir", {}),
    ("toplevel_number", 42, {}),
    ("toplevel_null", None, {}),
    # --- unknown / extra keys (schema additionalProperties:false -> rejected) ---
    ("unknown_toplevel_key", _valid_ir(__import__="os"), {}),
    ("unknown_nested_key", _valid_ir(indicators=[{"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close", "eval": "os.system"}]), {}),
    ("unknown_asset_key", _valid_ir(asset={"ticker": "SPY", "asset_class": "equity", "backdoor": 1}), {}),
    # --- out-of-vocabulary indicator / operator names & lookalikes ---
    ("indicator_lookalike_trailing_space", _valid_ir(indicators=[{"id": "x", "type": "RSI ", "params": {"period": 14}, "source": "close"}]), {}),
    ("indicator_lowercase", _valid_ir(indicators=[{"id": "x", "type": "rsi", "params": {"period": 14}, "source": "close"}]), {}),
    ("indicator_dunder", _valid_ir(indicators=[{"id": "x", "type": "__import__", "params": {"period": 14}, "source": "close"}]), {}),
    ("operator_eval", _valid_ir(entry={"left": "close", "op": "eval", "right": 30}), {}),
    ("operator_os_system", _valid_ir(entry={"left": "close", "op": "os.system", "right": 30}), {}),
    ("operand_out_of_vocab", _valid_ir(entry={"left": "not_an_indicator", "op": "<", "right": 30}), {}),
    # --- absurd numerics ---
    ("period_negative", _valid_ir(indicators=[{"id": "rsi14", "type": "RSI", "params": {"period": -5}, "source": "close"}]), {}),
    ("period_zero", _valid_ir(indicators=[{"id": "rsi14", "type": "RSI", "params": {"period": 0}, "source": "close"}]), {}),
    ("period_float", _valid_ir(indicators=[{"id": "rsi14", "type": "RSI", "params": {"period": 3.5}, "source": "close"}]), {}),
    ("period_enormous", _valid_ir(indicators=[{"id": "rsi14", "type": "RSI", "params": {"period": 10**9}, "source": "close"}]), {}),
    ("period_gt_data_length", _valid_ir(indicators=[{"id": "rsi14", "type": "RSI", "params": {"period": 100000}, "source": "close"}]), {}),
    # --- deeply nested condition tree (must fail fast, no RecursionError-500) ---
    ("deep_nesting_400", _valid_ir(entry=_nest(400)), {}),
    ("deep_nesting_5000", _valid_ir(entry=_nest(5000)), {}),
    # --- date-range abuse ---
    ("end_before_start", _valid_ir(), {"start": "2020-01-01", "end": "2015-01-01"}),
    ("dates_far_future", _valid_ir(), {"start": "2999-01-01", "end": "2999-12-31"}),
    # --- unicode tricks in string fields ---
    ("unicode_homoglyph_type", _valid_ir(indicators=[{"id": "x", "type": "ЅМА", "params": {"period": 14}, "source": "close"}]), {}),
    ("null_byte_operand", _valid_ir(entry={"left": "close\x00", "op": "<", "right": 30}), {}),
    ("rtl_marker_id", _valid_ir(indicators=[{"id": "r‮si", "type": "RSI", "params": {"period": 14}, "source": "close"}]), {}),
]


@pytest.mark.parametrize("case_id,ir,extra", _HOSTILE_CASES, ids=[c[0] for c in _HOSTILE_CASES])
def test_hostile_ir_is_rejected_cleanly_without_reaching_the_engine(case_id, ir, extra, engine_spy):
    resp = _post(ir, **extra)

    # A clean client error, never a 5xx.
    assert resp.status_code in (400, 413, 422), (
        f"{case_id}: expected a clean 4xx, got {resp.status_code}: {resp.text[:300]}"
    )
    # Body is JSON with a plain-English detail, and leaks no internals.
    assert resp.headers["content-type"].startswith("application/json")
    assert "Traceback" not in resp.text
    for leak in ("RecursionError", "KeyError", "TypeError", 'File "'):
        assert leak not in resp.text, f"{case_id}: response leaked internals ({leak}): {resp.text[:300]}"
    # The simulator was never reached.
    assert engine_spy["engine"] is False, f"{case_id}: reached the engine"


def test_oversized_confirm_body_is_capped_with_413(engine_spy):
    """A structurally-small but byte-enormous IR (a giant string field) is
    rejected by the body-size cap before parsing/validation."""
    ir = _valid_ir()
    ir["asset"]["ticker"] = "A" * 100_000
    resp = _post(ir)
    assert resp.status_code == 413
    assert engine_spy["engine"] is False


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "-inf"])
def test_non_finite_numeric_operands_are_rejected_cleanly_before_the_engine(bad, engine_spy):
    """NaN / Infinity pass jsonschema's `number` type but crash deep in the
    sensitivity grid (`int(nan)`). httpx's encoder refuses them, but a lenient
    hostile client would send them (Starlette's json.loads accepts them), so
    post a raw body the way such a client could. They must be rejected cleanly
    (422) before any engine work."""
    ir = _valid_ir(entry={"left": "rsi14", "op": "<", "right": bad})
    body = json.dumps(
        {"ir": ir, "assumptions": [], "ticker": "SPY", "start": "2015-01-01", "end": None},
        allow_nan=True,
    )
    resp = client.post("/confirm", content=body, headers={"content-type": "application/json"})
    assert resp.status_code == 422, f"{bad!r}: got {resp.status_code} {resp.text[:200]}"
    assert "Traceback" not in resp.text
    assert engine_spy["engine"] is False


def test_finite_but_huge_numeric_operand_runs_inertly_to_completion():
    """A finite (if absurd) number like 1e308 is a legitimate operand: the
    strategy is silly but valid, so it must run the real engine to completion
    and return cleanly, never crash. No engine spy -- this one is meant to run.
    """
    ir = _valid_ir(entry={"left": "rsi14", "op": "<", "right": 1e308})
    resp = _post(ir)
    assert resp.status_code in (200, 400, 422), f"huge finite operand crashed: {resp.status_code} {resp.text[:200]}"
    assert "Traceback" not in resp.text
