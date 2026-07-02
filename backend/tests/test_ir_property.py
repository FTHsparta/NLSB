"""Phase 8B: property-based validation of the /confirm IR boundary (INV-2).

The deployed boundary in front of the engine is two steps: `enforce_ir_complexity`
(the iterative pre-validation cap on depth / node count / non-finite numbers)
then `validate_ir` (the JSON schema). The invariant these tests pin: for ANY
randomly-generated JSON structure, that boundary either accepts it as a
well-typed IR or rejects it with one of exactly two clean error types --
`HTTPException` (the cap) or `jsonschema.ValidationError` (the schema). It must
NEVER leak a RecursionError, KeyError, TypeError, or any other exception class
to the caller. That is precisely INV-2.
"""

from __future__ import annotations

import jsonschema
import pytest
from fastapi import HTTPException
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.abuse import enforce_ir_complexity
from app.translation.interpreter import validate_ir

# The two -- and only two -- acceptable failure modes at the boundary.
CLEAN_REJECTIONS = (HTTPException, jsonschema.ValidationError)


def _run_boundary(candidate: object) -> None:
    """The deployed order: structural cap first, then schema validation."""
    enforce_ir_complexity(candidate)
    validate_ir(candidate)


# JSON-compatible values with bounded breadth/depth. Includes non-finite floats
# (NaN/Infinity) on purpose -- the cap must reject them cleanly, not crash.
_json = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(min_value=-(10**12), max_value=10**12)
    | st.floats(allow_nan=True, allow_infinity=True)
    | st.text(max_size=20),
    lambda children: st.lists(children, max_size=6)
    | st.dictionaries(st.text(max_size=12), children, max_size=6),
    max_leaves=40,
)


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(_json)
def test_boundary_only_ever_accepts_or_cleanly_rejects_random_json(candidate):
    try:
        _run_boundary(candidate)
    except CLEAN_REJECTIONS:
        pass  # a clean rejection is the expected outcome for (nearly) all input
    except Exception as exc:  # noqa: BLE001 - this is the whole point of the test
        pytest.fail(
            f"boundary leaked a non-clean {type(exc).__name__} for {candidate!r}: {exc}"
        )


# A strategy that mutates a valid IR skeleton -- these land much closer to the
# schema's decision surface than free-form JSON, exercising deeper validator
# paths (enum checks, additionalProperties, oneOf resolution) rather than
# bouncing off the top-level `type: object` check.
_operand = st.integers(min_value=-100, max_value=100) | st.text(max_size=8) | st.floats(allow_nan=True)
_op = st.sampled_from(["<", ">", "<=", ">=", "crosses_above", "crosses_below", "eval", "  ", "OR"])
_comparison = st.fixed_dictionaries({"left": _operand, "op": _op, "right": _operand})


@st.composite
def _fuzzed_ir(draw):
    return {
        "asset": {
            "ticker": draw(st.text(max_size=12)),
            "asset_class": draw(st.sampled_from(["equity", "etf", "crypto", "futures", "gold", ""])),
        },
        "indicators": draw(
            st.lists(
                st.fixed_dictionaries(
                    {
                        "id": st.text(max_size=8),
                        "type": st.sampled_from(["RSI", "SMA", "EMA", "rsi", "RSI ", "__import__"]),
                        "params": st.fixed_dictionaries({"period": st.integers(min_value=-5, max_value=500) | st.floats()}),
                        "source": st.sampled_from(["close", "open", "high", "low", "CLOSE", "adj"]),
                    }
                ),
                max_size=4,
            )
        ),
        "entry": draw(_comparison),
        "exit": draw(_comparison),
        "position": {"direction": draw(st.sampled_from(["long", "short", ""])), "size": draw(st.sampled_from(["full", "half"]))},
        "risk": draw(st.none() | st.fixed_dictionaries({"stop_loss_pct": st.floats() | st.none(), "take_profit_pct": st.floats() | st.none()})),
    }


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(_fuzzed_ir())
def test_boundary_only_ever_accepts_or_cleanly_rejects_ir_shaped_fuzz(candidate):
    try:
        _run_boundary(candidate)
    except CLEAN_REJECTIONS:
        pass
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"boundary leaked a non-clean {type(exc).__name__} for {candidate!r}: {exc}"
        )


@settings(max_examples=50, deadline=None)
@given(st.integers(min_value=0, max_value=5000))
def test_arbitrary_nesting_depth_never_recursion_errors(depth):
    """Directly target the RecursionError class of bug across a wide depth
    range: however deep the condition tree, the boundary returns a clean
    rejection, never a RecursionError."""
    cond = {"left": "close", "op": "<", "right": 30}
    for _ in range(depth):
        cond = {"all_of": [cond]}
    ir = {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [],
        "entry": cond,
        "exit": {"left": "close", "op": ">", "right": 30},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }
    try:
        _run_boundary(ir)
    except CLEAN_REJECTIONS:
        pass
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"depth={depth} leaked {type(exc).__name__}: {exc}")
