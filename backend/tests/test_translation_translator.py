import json

from app.translation import translator as translator_module
from app.translation.translator import MAX_RETRIES, translate_to_ir


class FakeLLMClient:
    """Returns canned responses in order; repeats the last one if exhausted."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, *, system, user):
        self.calls.append({"system": system, "user": user})
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[idx]


def _json(obj) -> str:
    return json.dumps(obj)


def test_simple_strategy_translates_with_period_assumption():
    sparse = {
        "asset": {"ticker": "SPY"},
        "indicators": [{"id": "rsi14", "type": "RSI"}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        "exit": {"left": "rsi14", "op": ">", "right": 70},
    }
    client = FakeLLMClient([_json(sparse)])
    result = translate_to_ir("buy SPY when RSI drops below 30, sell when RSI exceeds 70", client)

    assert result.status == "ok"
    assert result.full_ir["asset"]["ticker"] == "SPY"
    fields = {a.field for a in result.assumptions}
    assert "indicators.rsi14.params.period" in fields
    assert any(a.value == 14 for a in result.assumptions if a.field.endswith("params.period"))


def test_compound_strategy_produces_multi_condition_ir():
    sparse = {
        "asset": {"ticker": "SPY"},
        "indicators": [
            {"id": "rsi14", "type": "RSI", "params": {"period": 14}},
            {"id": "sma50", "type": "SMA", "params": {"period": 50}},
            {"id": "sma200", "type": "SMA", "params": {"period": 200}},
        ],
        "entry": {
            "all_of": [
                {"left": "rsi14", "op": "<", "right": 30},
                {"left": "sma50", "op": ">", "right": "sma200"},
            ]
        },
        "exit": {"left": "rsi14", "op": ">", "right": 70},
    }
    client = FakeLLMClient([_json(sparse)])
    result = translate_to_ir(
        "buy SPY when RSI < 30 and the 50-day MA is above the 200-day; sell when RSI > 70",
        client,
    )

    assert result.status == "ok"
    assert "all_of" in result.full_ir["entry"]
    assert len(result.full_ir["entry"]["all_of"]) == 2


def test_underspecified_strategy_surfaces_large_assumptions_list():
    sparse = {
        "asset": {"ticker": "SPY"},
        "indicators": [{"id": "rsi14", "type": "RSI"}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
    }
    client = FakeLLMClient([_json(sparse)])
    result = translate_to_ir("buy when oversold", client)

    assert result.status == "ok"
    # period, source, exit, asset_class, position x2, risk -> at least 5 distinct gaps
    assert len(result.assumptions) >= 5


def test_unsupported_request_returns_clean_result():
    client = FakeLLMClient(
        [_json({"unsupported": True, "reason": "Intraday data isn't supported in v1."})]
    )
    result = translate_to_ir("buy SPY every 5 minutes when RSI < 30", client)

    assert result.status == "unsupported"
    assert "v1" in result.message
    assert result.full_ir is None


def test_retry_loop_recovers_from_invalid_json():
    valid = {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [
            {"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}
        ],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        "exit": {"left": "rsi14", "op": ">", "right": 70},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }
    client = FakeLLMClient(["Sure! Here's the IR: {not valid json", _json(valid)])
    result = translate_to_ir("buy SPY when RSI < 30, sell when RSI > 70", client)

    assert result.status == "ok"
    assert len(result.attempts) == 2
    assert result.attempts[0].error is not None
    assert result.attempts[1].error is None
    # the retry prompt must carry the exact prior error forward
    assert "not valid JSON" in client.calls[1]["user"] or "JSON" in client.calls[1]["user"]


def test_retry_loop_recovers_from_schema_validation_failure():
    missing_position_size = {
        "asset": {"ticker": "SPY"},
        "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        "exit": {"left": "rsi14", "op": ">", "right": 70},
    }
    # malformed beyond what defaults.py can fix: indicator with unknown type
    invalid_type = {
        "asset": {"ticker": "SPY"},
        "indicators": [{"id": "foo", "type": "MACD", "params": {"period": 14}, "source": "close"}],
        "entry": {"left": "foo", "op": "<", "right": 30},
    }
    client = FakeLLMClient([_json(invalid_type), _json(missing_position_size)])
    result = translate_to_ir("buy SPY on a MACD signal", client)

    assert result.status == "ok"
    assert len(result.attempts) == 2
    assert result.attempts[0].error is not None


def test_unsupported_sentinel_short_circuits_before_defaulting(monkeypatch):
    """The sentinel has neither asset.ticker nor entry, so apply_defaults would
    raise DefaultingError on it. translate_to_ir must detect the sentinel and
    return before ever calling apply_defaults."""

    def _apply_defaults_must_not_be_called(*args, **kwargs):
        raise AssertionError("apply_defaults must not be called for an unsupported request")

    monkeypatch.setattr(
        translator_module, "apply_defaults", _apply_defaults_must_not_be_called
    )

    client = FakeLLMClient(
        [_json({"unsupported": True, "reason": "Multi-asset strategies aren't supported in v1."})]
    )
    result = translate_to_ir("trade BTC based on SPY's price action", client)

    assert result.status == "unsupported"
    assert "v1" in result.message
    assert len(result.attempts) == 1


def test_retries_exhausted_returns_structured_error():
    client = FakeLLMClient(["still not json {", "still not json {", "still not json {"])
    result = translate_to_ir("buy SPY when RSI < 30", client, max_retries=MAX_RETRIES)

    assert result.status == "error"
    assert len(result.attempts) == MAX_RETRIES
    assert "after 3 attempts" in result.message
