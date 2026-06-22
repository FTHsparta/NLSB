import copy

from app.translation.defaults import NO_EXIT_CONDITION, apply_defaults
from app.translation.renderer import render_confirmation


def _full_ir_and_assumptions():
    sparse = {
        "asset": {"ticker": "SPY"},
        "indicators": [{"id": "rsi14", "type": "RSI"}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        "exit": {"left": "rsi14", "op": ">", "right": 70},
    }
    return apply_defaults(sparse)


def test_renderer_is_pure_and_deterministic():
    full_ir, assumptions = _full_ir_and_assumptions()
    out1 = render_confirmation(full_ir, assumptions)
    out2 = render_confirmation(copy.deepcopy(full_ir), list(assumptions))
    assert out1 == out2


def test_renderer_mentions_ticker_and_conditions():
    full_ir, assumptions = _full_ir_and_assumptions()
    text = render_confirmation(full_ir, assumptions)
    assert "SPY" in text
    assert "RSI(14) is below 30" in text
    assert "RSI(14) is above 70" in text


def test_renderer_lists_assumptions_section():
    full_ir, assumptions = _full_ir_and_assumptions()
    text = render_confirmation(full_ir, assumptions)
    assert "I assumed (you didn't specify these):" in text
    # period and source were unstated for rsi14
    assert "indicators.rsi14.params.period" in text
    assert "indicators.rsi14.source" in text


def test_renderer_changes_when_ir_field_mutated():
    full_ir, assumptions = _full_ir_and_assumptions()
    base_text = render_confirmation(full_ir, assumptions)

    mutated = copy.deepcopy(full_ir)
    mutated["entry"]["right"] = 25
    mutated_text = render_confirmation(mutated, assumptions)

    assert base_text != mutated_text
    assert "is below 25" in mutated_text
    assert "is below 30" not in mutated_text


def test_renderer_stated_section_excludes_assumed_exit():
    full_ir, assumptions = _full_ir_and_assumptions()
    text = render_confirmation(full_ir, assumptions)
    # exit was explicitly stated in this fixture -> should be in "You specified"
    you_specified, _, i_assumed = text.partition("I assumed")
    assert "exit condition" in you_specified
    assert "- exit:" not in i_assumed


def test_renderer_no_assumptions_message_when_everything_stated():
    sparse = {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [
            {"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}
        ],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        "exit": {"left": "rsi14", "op": ">", "right": 70},
        "position": {"direction": "long", "size": "full"},
        "risk": {"stop_loss_pct": None, "take_profit_pct": None},
    }
    full_ir, assumptions = apply_defaults(sparse)
    assert assumptions == []
    text = render_confirmation(full_ir, assumptions)
    assert "(nothing — you specified every field)" in text


def test_renderer_renders_compound_condition():
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
    }
    full_ir, assumptions = apply_defaults(sparse)
    text = render_confirmation(full_ir, assumptions)
    assert "AND" in text
    assert "SMA(50) is above SMA(200)" in text


def test_no_exit_sentinel_renders_as_honest_prose_not_raw_condition():
    full_ir, assumptions = _full_ir_and_assumptions_no_exit()
    text = render_confirmation(full_ir, assumptions)

    assert "approximate buy-and-hold" in text
    assert "held the position from your first entry signal" in text
    # the literal sentinel must never leak into the rendered text
    assert "close < close" not in text
    assert "close price is below close price" not in text
    assert "is below close" not in text


def test_no_exit_warning_appears_in_prominent_heads_up_section_before_routine_notes():
    full_ir, assumptions = _full_ir_and_assumptions_no_exit()
    text = render_confirmation(full_ir, assumptions)

    assert "Heads up" in text
    heads_up_idx = text.index("Heads up")
    routine_idx = text.index("I assumed (you didn't specify these):")
    assert heads_up_idx < routine_idx

    # the no-exit reason text appears in the heads-up section, not buried in
    # the routine list as a field/value pair
    heads_up_section = text[heads_up_idx:routine_idx]
    assert "buy-and-hold" in heads_up_section


def test_routine_assumptions_section_excludes_the_warning_item():
    full_ir, assumptions = _full_ir_and_assumptions_no_exit()
    text = render_confirmation(full_ir, assumptions)

    routine_idx = text.index("I assumed (you didn't specify these):")
    routine_section = text[routine_idx:]
    assert "- exit:" not in routine_section


def test_renderer_no_warnings_omits_heads_up_section():
    full_ir, assumptions = _full_ir_and_assumptions()  # exit is stated here
    text = render_confirmation(full_ir, assumptions)
    assert "Heads up" not in text


def _full_ir_and_assumptions_no_exit():
    sparse = {
        "asset": {"ticker": "SPY"},
        "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
    }
    full_ir, assumptions = apply_defaults(sparse)
    assert full_ir["exit"] == NO_EXIT_CONDITION  # sanity: this fixture exercises the sentinel
    return full_ir, assumptions
