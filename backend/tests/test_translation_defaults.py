import pytest

from app.translation.defaults import (
    DEFAULT_ASSET_CLASS,
    DEFAULT_RSI_PERIOD,
    NO_EXIT_CONDITION,
    SEVERITY_NOTE,
    SEVERITY_WARNING,
    Assumption,
    DefaultingError,
    apply_defaults,
)


def _sparse(**overrides):
    base = {
        "asset": {"ticker": "SPY"},
        "indicators": [{"id": "rsi14", "type": "RSI"}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
    }
    base.update(overrides)
    return base


def test_unstated_rsi_period_defaults_to_14():
    full_ir, assumptions = apply_defaults(_sparse())
    rsi = next(i for i in full_ir["indicators"] if i["id"] == "rsi14")
    assert rsi["params"]["period"] == DEFAULT_RSI_PERIOD
    fields = {a.field for a in assumptions}
    assert "indicators.rsi14.params.period" in fields


def test_stated_period_is_not_overwritten_or_flagged():
    sparse = _sparse(indicators=[{"id": "rsi14", "type": "RSI", "params": {"period": 21}}])
    full_ir, assumptions = apply_defaults(sparse)
    rsi = full_ir["indicators"][0]
    assert rsi["params"]["period"] == 21
    assert not any(a.field == "indicators.rsi14.params.period" for a in assumptions)


def test_unstated_source_defaults_to_close():
    full_ir, assumptions = apply_defaults(_sparse())
    rsi = full_ir["indicators"][0]
    assert rsi["source"] == "close"
    assert any(a.field == "indicators.rsi14.source" for a in assumptions)


def test_missing_ticker_raises_defaulting_error():
    with pytest.raises(DefaultingError):
        apply_defaults({"entry": {"left": "close", "op": "<", "right": 30}})


def test_missing_entry_raises_defaulting_error():
    with pytest.raises(DefaultingError):
        apply_defaults({"asset": {"ticker": "SPY"}})


def test_unstated_exit_defaults_to_never_fires_sentinel():
    full_ir, assumptions = apply_defaults(_sparse())
    assert full_ir["exit"] == NO_EXIT_CONDITION
    assert any(a.field == "exit" for a in assumptions)


def test_unstated_exit_assumption_is_elevated_severity():
    _, assumptions = apply_defaults(_sparse())
    exit_assumption = next(a for a in assumptions if a.field == "exit")
    assert exit_assumption.severity == SEVERITY_WARNING


def test_routine_assumptions_stay_at_note_severity():
    _, assumptions = apply_defaults(_sparse())
    routine = [a for a in assumptions if a.field != "exit"]
    assert routine  # sanity: there are routine assumptions in this fixture
    assert all(a.severity == SEVERITY_NOTE for a in routine)


def test_stated_exit_is_preserved():
    sparse = _sparse(exit={"left": "rsi14", "op": ">", "right": 70})
    full_ir, assumptions = apply_defaults(sparse)
    assert full_ir["exit"] == {"left": "rsi14", "op": ">", "right": 70}
    assert not any(a.field == "exit" for a in assumptions)


def test_unstated_asset_class_defaults_to_equity_without_a_user_facing_assumption():
    """REWRITTEN (pre-launch honesty pass): this previously asserted an
    `asset.asset_class` Assumption was recorded. Assumptions are user-facing
    copy (every one renders in the "I assumed" list), and asset_class is
    decorative — nothing in the data or cost layer reads it — so announcing
    it implied a per-asset-class capability the engine lacks. The field is
    still filled (the schema requires it) but silently, as internal plumbing."""
    full_ir, assumptions = apply_defaults(_sparse())
    assert full_ir["asset"]["asset_class"] == DEFAULT_ASSET_CLASS
    assert not any(a.field == "asset.asset_class" for a in assumptions)


def test_unstated_position_defaults_to_long_full():
    full_ir, assumptions = apply_defaults(_sparse())
    assert full_ir["position"] == {"direction": "long", "size": "full"}
    fields = {a.field for a in assumptions}
    assert "position.direction" in fields
    assert "position.size" in fields


def test_unstated_risk_defaults_to_none():
    full_ir, assumptions = apply_defaults(_sparse())
    assert full_ir["risk"] is None
    assert any(a.field == "risk" for a in assumptions)


def test_partial_risk_fills_missing_key():
    sparse = _sparse(risk={"stop_loss_pct": 0.05})
    full_ir, assumptions = apply_defaults(sparse)
    assert full_ir["risk"]["stop_loss_pct"] == 0.05
    assert full_ir["risk"]["take_profit_pct"] is None
    assert any(a.field == "risk.take_profit_pct" for a in assumptions)
    assert not any(a.field == "risk.stop_loss_pct" for a in assumptions)


def test_apply_defaults_does_not_mutate_input():
    sparse = _sparse()
    original = {**sparse, "asset": dict(sparse["asset"])}
    apply_defaults(sparse)
    assert sparse["asset"] == original["asset"]
    assert "asset_class" not in sparse["asset"]


def test_assumption_is_frozen_dataclass():
    a = Assumption(field="x", value=1, reason="why")
    with pytest.raises(Exception):
        a.field = "y"
