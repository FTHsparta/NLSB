import pytest

from app.robustness.params import extract_tunable_params, get_in, set_in_copy


def _simple_ir():
    return {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [
            {"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}
        ],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        "exit": {"left": "rsi14", "op": ">", "right": 70},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }


def _compound_ir():
    return {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [
            {"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"},
            {"id": "sma50", "type": "SMA", "params": {"period": 50}, "source": "close"},
            {"id": "sma200", "type": "SMA", "params": {"period": 200}, "source": "close"},
        ],
        "entry": {
            "all_of": [
                {"left": "rsi14", "op": "<", "right": 30},
                {"left": "sma50", "op": ">", "right": "sma200"},
            ]
        },
        "exit": {"left": "rsi14", "op": ">", "right": 70},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }


def test_extracts_indicator_period():
    params = extract_tunable_params(_simple_ir())
    period_params = [p for p in params if p.kind == "period"]
    assert len(period_params) == 1
    assert period_params[0].param_id == "indicators.rsi14.period"
    assert period_params[0].value == 14


def test_period_grid_matches_documented_rule():
    params = extract_tunable_params(_simple_ir())
    period_param = next(p for p in params if p.kind == "period")
    assert period_param.grid == (10, 12, 14, 16, 18)


def test_period_grid_clips_below_one():
    ir = _simple_ir()
    ir["indicators"][0]["params"]["period"] = 2
    params = extract_tunable_params(ir)
    period_param = next(p for p in params if p.kind == "period")
    # offsets -4,-2,0,2,4 on period=2 -> -2,0,2,4,6 clipped to >=1 -> {1,1,2,4,6} dedup
    assert period_param.grid == (1, 2, 4, 6)


def test_extracts_thresholds_from_entry_and_exit():
    params = extract_tunable_params(_simple_ir())
    threshold_params = [p for p in params if p.kind == "threshold"]
    values = sorted(p.value for p in threshold_params)
    assert values == [30, 70]


def test_threshold_grid_matches_documented_rule():
    params = extract_tunable_params(_simple_ir())
    entry_threshold = next(p for p in params if p.kind == "threshold" and p.value == 30)
    # step = max(1, round(30*0.1)) = 3 -> [24, 27, 30, 33, 36]
    assert entry_threshold.grid == (24, 27, 30, 33, 36)


def test_does_not_extract_indicator_ids_or_price_fields_as_thresholds():
    params = extract_tunable_params(_compound_ir())
    threshold_values = [p.value for p in params if p.kind == "threshold"]
    # "sma50" > "sma200" comparison must NOT produce a threshold (both sides
    # are indicator ids, not numeric constants).
    assert 30 in threshold_values
    assert 70 in threshold_values
    assert len(threshold_values) == 2


def test_extracts_periods_for_every_indicator_in_compound_strategy():
    params = extract_tunable_params(_compound_ir())
    period_ids = {p.param_id for p in params if p.kind == "period"}
    assert period_ids == {
        "indicators.rsi14.period",
        "indicators.sma50.period",
        "indicators.sma200.period",
    }


def test_no_exit_sentinel_yields_no_exit_thresholds():
    ir = _simple_ir()
    ir["exit"] = {"left": "close", "op": "<", "right": "close"}  # NO_EXIT_CONDITION
    params = extract_tunable_params(ir)
    exit_thresholds = [p for p in params if p.param_id.startswith("exit.")]
    assert exit_thresholds == []


def test_path_round_trips_through_get_in_and_set_in_copy():
    ir = _compound_ir()
    params = extract_tunable_params(ir)
    sma50_period = next(p for p in params if p.param_id == "indicators.sma50.period")

    assert get_in(ir, sma50_period.path) == 50

    mutated = set_in_copy(ir, sma50_period.path, 75)
    assert get_in(mutated, sma50_period.path) == 75
    # original untouched
    assert get_in(ir, sma50_period.path) == 50


def test_compound_entry_threshold_path_resolves_correctly():
    ir = _compound_ir()
    params = extract_tunable_params(ir)
    entry_threshold = next(p for p in params if p.kind == "threshold" and p.value == 30)
    assert get_in(ir, entry_threshold.path) == 30
    mutated = set_in_copy(ir, entry_threshold.path, 20)
    assert mutated["entry"]["all_of"][0]["right"] == 20
    assert ir["entry"]["all_of"][0]["right"] == 30


def test_set_in_copy_does_not_mutate_original_nested_structures():
    ir = _compound_ir()
    original_indicators = ir["indicators"]
    set_in_copy(ir, ("indicators", 0, "params", "period"), 999)
    assert ir["indicators"] is original_indicators
    assert ir["indicators"][0]["params"]["period"] == 14
