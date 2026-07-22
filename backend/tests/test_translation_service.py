import json

import numpy as np
import pandas as pd
import pytest

from app.translation import service


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


def test_translate_returns_ir_and_restatement_without_running_backtest(monkeypatch):
    called = {"run": False}

    def _spy_run_ir_backtest(*args, **kwargs):
        called["run"] = True
        raise AssertionError("run_ir_backtest must not be called by translate()")

    monkeypatch.setattr(service, "run_ir_backtest", _spy_run_ir_backtest)

    client = FakeLLMClient([json.dumps(_SIMPLE_SPARSE_IR)])
    response = service.translate(
        "buy SPY when RSI drops below 30, sell when RSI exceeds 70", llm_client=client
    )

    assert response.status == "ok"
    assert response.ir is not None
    assert response.restatement is not None
    assert "SPY" in response.restatement
    assert called["run"] is False


def test_translate_propagates_unsupported_status():
    client = FakeLLMClient(
        [json.dumps({"unsupported": True, "reason": "Options aren't supported in v1."})]
    )
    response = service.translate("buy SPY call options when RSI < 30", llm_client=client)

    assert response.status == "unsupported"
    assert response.ir is None
    assert "v1" in response.message


def test_confirm_runs_backtest_and_returns_result():
    from app.translation.defaults import apply_defaults

    close = _oscillating_close()
    price_data = _price_data(close)
    full_ir, _assumptions = apply_defaults(_SIMPLE_SPARSE_IR)
    result = service.confirm(full_ir, price_data)

    assert result.num_trades >= 0
    assert isinstance(result.total_return, float)


def test_confirm_rejects_invalid_ir():
    close = _oscillating_close()
    price_data = _price_data(close)
    with pytest.raises(Exception):
        service.confirm({"not": "a valid ir"}, price_data)


_STOP_BEARING_SPARSE_IR = {
    "asset": {"ticker": "SPY"},
    "indicators": [{"id": "rsi14", "type": "RSI"}],
    "entry": {"left": "rsi14", "op": "<", "right": 30},
    "exit": {"left": "rsi14", "op": ">", "right": 70},
    "risk": {"stop_loss_pct": 0.05},
}


def test_translate_rejects_stop_loss_via_unsupported_path_never_reaching_gate():
    """Pre-launch honesty fix: the engine never simulates stops (interpret_ir
    doesn't read ir["risk"]; no sl_stop/tp_stop reaches vectorbt), so a
    stop-bearing IR must be rejected DETERMINISTICALLY — the LLM won't
    self-reject it (it's schema-valid). status="unsupported" with no
    restatement means the frontend structurally cannot mount the gate
    (atGate requires status ok AND a restatement)."""
    client = FakeLLMClient([json.dumps(_STOP_BEARING_SPARSE_IR)])
    response = service.translate("buy SPY when RSI < 30, sell at 70, 5% stop loss", llm_client=client)

    assert response.status == "unsupported"
    assert response.ir is None
    assert response.restatement is None
    assert "stop-loss" in response.message
    assert "different strategy" in response.message


def test_translate_rejects_take_profit_and_names_it():
    sparse = {**_STOP_BEARING_SPARSE_IR, "risk": {"take_profit_pct": 0.10}}
    client = FakeLLMClient([json.dumps(sparse)])
    response = service.translate("buy SPY when RSI < 30, take profit at 10%", llm_client=client)

    assert response.status == "unsupported"
    assert "take-profit" in response.message


def test_translate_rejects_combined_stop_and_target_naming_both():
    sparse = {**_STOP_BEARING_SPARSE_IR, "risk": {"stop_loss_pct": 0.05, "take_profit_pct": 0.10}}
    client = FakeLLMClient([json.dumps(sparse)])
    response = service.translate("buy SPY when RSI < 30, 5% stop, 10% target", llm_client=client)

    assert response.status == "unsupported"
    assert "a stop-loss and a take-profit" in response.message


def test_translate_with_null_risk_still_reaches_gate_unchanged():
    """The rejection triggers on stated VALUES only — a null/absent risk
    block (the overwhelmingly common case) proceeds to a normal gate payload."""
    sparse = {**_STOP_BEARING_SPARSE_IR, "risk": {"stop_loss_pct": None, "take_profit_pct": None}}
    client = FakeLLMClient([json.dumps(sparse)])
    response = service.translate("buy SPY when RSI < 30, sell when RSI > 70", llm_client=client)

    assert response.status == "ok"
    assert response.ir is not None
    assert response.restatement is not None


def test_confirm_robustness_rejects_stop_bearing_ir_posted_directly():
    """Defence in depth: even bypassing /translate entirely (a hand-crafted
    POST /confirm), a stop-bearing IR must never produce results — the same
    guard runs at the only run path."""
    from app.translation.defaults import apply_defaults
    from app.translation.interpreter import IRInterpreterError

    close = _oscillating_close()
    price_data = _price_data(close)
    full_ir, assumptions = apply_defaults(_STOP_BEARING_SPARSE_IR)

    with pytest.raises(IRInterpreterError, match="stop-loss"):
        service.confirm_robustness(full_ir, price_data, assumptions)

    with pytest.raises(IRInterpreterError, match="stop-loss"):
        service.confirm(full_ir, price_data)


def test_correct_re_translates_with_correction_context():
    prior_ir = {"asset": {"ticker": "SPY"}, "entry": {"left": "close", "op": "<", "right": 30}}
    corrected_sparse = {
        "asset": {"ticker": "SPY"},
        "indicators": [{"id": "rsi14", "type": "RSI"}],
        "entry": {"left": "rsi14", "op": "<", "right": 25},
        "exit": {"left": "rsi14", "op": ">", "right": 70},
    }
    client = FakeLLMClient([json.dumps(corrected_sparse)])

    response = service.correct(
        "buy SPY when oversold",
        prior_ir,
        "I meant RSI below 25, using the actual RSI indicator, not raw close price",
        llm_client=client,
    )

    assert response.status == "ok"
    assert response.ir["entry"]["right"] == 25
    # the correction text must have actually reached the model
    assert "RSI below 25" in client.calls[0]["user"]
