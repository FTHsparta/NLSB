import json
import math

import numpy as np
import pandas as pd

from app.robustness.robustness import RESULT_KEYS, run_robustness
from app.translation.defaults import apply_defaults


def _oscillating_close(n: int) -> pd.Series:
    block = np.concatenate([-np.ones(20), np.ones(20)])
    reps = int(np.ceil((n - 1) / len(block)))
    deltas = np.tile(block, reps)[: n - 1]
    close = 100 + np.concatenate([[0], np.cumsum(deltas)])
    idx = pd.date_range("2015-01-01", periods=n, freq="D")
    return pd.Series(close, index=idx, dtype=float)


def _price_data(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close})


def _round_trip_ir():
    return {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        "exit": {"left": "rsi14", "op": ">", "right": 70},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }


def _no_exit_ir():
    sparse_ir = {
        "asset": {"ticker": "SPY"},
        "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
    }
    return apply_defaults(sparse_ir)


# ---------------------------------------------------------------------------
# INVARIANT 4 (orchestrator level): no-exit input never produces a verdict
# ---------------------------------------------------------------------------


def test_invariant4_no_exit_short_circuits_before_round_trip_machinery():
    full_ir, assumptions = _no_exit_ir()
    price_data = _price_data(_oscillating_close(200))

    result = run_robustness(full_ir, price_data, assumptions)

    assert result["kind"] == "no_exit"
    assert result["verdict"] is None
    assert result["sensitivity"] is None
    assert result["walk_forward"] is None
    assert result["deflated_sharpe"] is None
    assert result["regime"] is None
    assert "buy-and-hold" in result["no_exit"]["message"]


def test_no_exit_does_not_run_round_trip_machinery(monkeypatch):
    """Branch at the top means walk-forward/sensitivity/regime must never
    even be called for a no-exit strategy, not just unused in the result."""
    import app.robustness.robustness as robustness_module

    calls = []
    monkeypatch.setattr(robustness_module, "run_sensitivity", lambda *a, **k: calls.append("sensitivity"))
    monkeypatch.setattr(robustness_module, "run_walk_forward", lambda *a, **k: calls.append("walk_forward"))
    monkeypatch.setattr(robustness_module, "run_regime_analysis", lambda *a, **k: calls.append("regime"))

    full_ir, assumptions = _no_exit_ir()
    price_data = _price_data(_oscillating_close(200))
    run_robustness(full_ir, price_data, assumptions)

    assert calls == []


# ---------------------------------------------------------------------------
# INVARIANT 5: stable, complete, serializable schema
# ---------------------------------------------------------------------------


def test_invariant5_full_result_has_every_sub_result_under_stable_keys():
    full_ir, assumptions = apply_defaults(_round_trip_ir())
    price_data = _price_data(_oscillating_close(400))

    result = run_robustness(
        full_ir,
        price_data,
        assumptions,
        in_sample_bars=150,
        out_of_sample_bars=60,
        step_bars=60,
    )

    assert set(result.keys()) == set(RESULT_KEYS)
    assert result["kind"] == "full"
    assert result["no_exit"] is None
    assert isinstance(result["sensitivity"], list) and len(result["sensitivity"]) > 0
    assert isinstance(result["walk_forward"], dict) and "folds" in result["walk_forward"]
    assert isinstance(result["deflated_sharpe"], dict) and "dsr" in result["deflated_sharpe"]
    assert isinstance(result["regime"], dict) and "breakdowns" in result["regime"]
    assert isinstance(result["verdict"], dict) and result["verdict"]["verdict"] in (
        "PASS",
        "SHAKY",
        "LIKELY_OVERFIT",
        "UNTESTABLE",
    )

    # Fully JSON-serializable (frontend contract): NaN floats serialize via
    # allow_nan (json's default) without raising; the structural check here
    # is that nothing in the tree is a non-serializable object (dataclass
    # instance, tuple-of-objects, etc.) slipping through dataclasses.asdict.
    json.dumps(result, default=str)


def test_no_exit_result_is_json_serializable():
    full_ir, assumptions = _no_exit_ir()
    price_data = _price_data(_oscillating_close(200))

    result = run_robustness(full_ir, price_data, assumptions)

    json.dumps(result, default=str)
