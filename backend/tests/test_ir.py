"""Phase 2 tests: JSON schema validation and safe interpreter.

Test groups
-----------
1. Schema validation — valid IR passes; malformed IR is rejected.
2. Interpreter whitelist — rejects unknown indicator types and operators
   (defence-in-depth; schema already enforces these, but interpreter checks
   independently).
3. Regression gate — IR path vs. hardcoded Phase 1 path must be bit-identical
   on the same synthetic price series.  Any divergence means the interpreter
   has a bug.
4. Compound strategy — RSI<30 AND SMA50>SMA200 produces signals that are a
   strict subset of RSI-alone signals (AND is stricter than OR/single condition).
"""

import numpy as np
import pandas as pd
import pytest
import jsonschema

from app.engine.backtest import run_ir_backtest, run_rsi_backtest
from app.translation.interpreter import (
    IRInterpreterError,
    compute_ir_warmup,
    interpret_ir,
    validate_ir,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

RSI14_SPY_IR = {
    "asset": {"ticker": "SPY", "asset_class": "etf"},
    "indicators": [
        {"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}
    ],
    "entry": {"all_of": [{"left": "rsi14", "op": "<", "right": 30}]},
    "exit": {"any_of": [{"left": "rsi14", "op": ">", "right": 70}]},
    "position": {"direction": "long", "size": "full"},
    "risk": {"stop_loss_pct": None, "take_profit_pct": None},
}


def _oscillating_close(n: int = 200) -> pd.Series:
    """Sharp oscillating series that pushes RSI through both thresholds."""
    block = np.concatenate([-np.ones(20), np.ones(20)])
    reps = int(np.ceil((n - 1) / len(block)))
    deltas = np.tile(block, reps)[: n - 1]
    close = 100 + np.concatenate([[0], np.cumsum(deltas)])
    idx = pd.date_range("2015-01-01", periods=n, freq="D")
    return pd.Series(close, index=idx, dtype=float)


def _price_data(close: pd.Series) -> pd.DataFrame:
    """Minimal OHLC DataFrame (all columns equal to close — enough for the tests)."""
    return pd.DataFrame(
        {"Open": close, "High": close, "Low": close, "Close": close}
    )


# ---------------------------------------------------------------------------
# 1. Schema validation
# ---------------------------------------------------------------------------


def test_valid_ir_passes_schema():
    validate_ir(RSI14_SPY_IR)  # must not raise


def test_schema_rejects_missing_required_field():
    bad = {k: v for k, v in RSI14_SPY_IR.items() if k != "entry"}
    with pytest.raises(jsonschema.ValidationError):
        validate_ir(bad)


def test_schema_rejects_unknown_indicator_type():
    bad = {
        **RSI14_SPY_IR,
        "indicators": [
            {"id": "macd", "type": "MACD", "params": {"period": 12}, "source": "close"}
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_ir(bad)


def test_schema_rejects_unknown_operator():
    bad = {
        **RSI14_SPY_IR,
        "entry": {"all_of": [{"left": "rsi14", "op": "!=", "right": 30}]},
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_ir(bad)


def test_schema_rejects_invalid_asset_class():
    bad = {**RSI14_SPY_IR, "asset": {"ticker": "SPY", "asset_class": "bond"}}
    with pytest.raises(jsonschema.ValidationError):
        validate_ir(bad)


def test_schema_rejects_non_integer_period():
    bad = {
        **RSI14_SPY_IR,
        "indicators": [
            {"id": "rsi14", "type": "RSI", "params": {"period": 14.5}, "source": "close"}
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_ir(bad)


def test_schema_accepts_null_risk():
    ir = {**RSI14_SPY_IR, "risk": None}
    validate_ir(ir)  # must not raise


def test_schema_accepts_absent_risk():
    ir = {k: v for k, v in RSI14_SPY_IR.items() if k != "risk"}
    validate_ir(ir)  # must not raise


def test_schema_accepts_compound_any_of_condition():
    ir = {
        **RSI14_SPY_IR,
        "exit": {
            "any_of": [
                {"left": "rsi14", "op": ">", "right": 70},
                {"left": "rsi14", "op": "crosses_above", "right": 50},
            ]
        },
    }
    validate_ir(ir)  # must not raise


def test_schema_rejects_empty_all_of():
    bad = {**RSI14_SPY_IR, "entry": {"all_of": []}}
    with pytest.raises(jsonschema.ValidationError):
        validate_ir(bad)


# ---------------------------------------------------------------------------
# 2. Interpreter whitelist (defence-in-depth; validate=False bypasses schema
#    so we can exercise the interpreter's own checks in isolation)
# ---------------------------------------------------------------------------


def test_interpreter_rejects_unknown_indicator_type():
    bad_ir = {
        **RSI14_SPY_IR,
        "indicators": [
            {"id": "macd", "type": "MACD", "params": {"period": 12}, "source": "close"}
        ],
    }
    close = _oscillating_close()
    with pytest.raises(IRInterpreterError, match="MACD"):
        interpret_ir(bad_ir, _price_data(close), validate=False)


def test_interpreter_rejects_unknown_operator():
    bad_ir = {
        **RSI14_SPY_IR,
        "entry": {"all_of": [{"left": "rsi14", "op": "!=", "right": 30}]},
    }
    close = _oscillating_close()
    with pytest.raises(IRInterpreterError, match="!="):
        interpret_ir(bad_ir, _price_data(close), validate=False)


def test_interpreter_rejects_unresolvable_operand():
    bad_ir = {
        **RSI14_SPY_IR,
        "entry": {"all_of": [{"left": "nonexistent", "op": "<", "right": 30}]},
    }
    close = _oscillating_close()
    with pytest.raises(IRInterpreterError, match="nonexistent"):
        interpret_ir(bad_ir, _price_data(close), validate=False)


# ---------------------------------------------------------------------------
# 3. Regression gate — IR path must match the hardcoded Phase 1 path exactly
# ---------------------------------------------------------------------------


def test_ir_regression_matches_hardcoded_rsi_strategy():
    """Critical gate: IR path and Phase 1 hardcoded path must agree on every metric.

    Uses the synthetic oscillating series (deterministic, no network) so
    the comparison is exact and repeatable.  Any divergence means the
    interpreter introduces a bug relative to the known-good hardcoded path.
    """
    close = _oscillating_close()
    price_data = _price_data(close)

    # Hardcoded Phase 1 path (the ground truth)
    hardcoded = run_rsi_backtest(close, rsi_period=14, fees=0.0, slippage=0.0)

    # IR path (the new route under test)
    ir_result = run_ir_backtest(RSI14_SPY_IR, price_data, fees=0.0, slippage=0.0)

    assert ir_result.num_trades == hardcoded.num_trades, (
        f"Trade count mismatch: IR={ir_result.num_trades}, hardcoded={hardcoded.num_trades}"
    )
    assert ir_result.total_return == pytest.approx(hardcoded.total_return, rel=1e-9), (
        f"Total return mismatch: IR={ir_result.total_return:.6f}, hardcoded={hardcoded.total_return:.6f}"
    )
    assert ir_result.start == hardcoded.start
    assert ir_result.end == hardcoded.end
    assert ir_result.max_drawdown == pytest.approx(hardcoded.max_drawdown, rel=1e-9)


def test_ir_warmup_matches_hardcoded_phase1_convention():
    """compute_ir_warmup for RSI(14) must equal phase1_slice.py's warmup = period + 1."""
    warmup = compute_ir_warmup(RSI14_SPY_IR)
    assert warmup == 14 + 1  # matches run_rsi_backtest(rsi_period=14): warmup = rsi_period + 1


# ---------------------------------------------------------------------------
# 4. Compound strategy — RSI<30 AND SMA50>SMA200
# ---------------------------------------------------------------------------

_COMPOUND_IR = {
    "asset": {"ticker": "TEST", "asset_class": "equity"},
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
    "exit": {"any_of": [{"left": "rsi14", "op": ">", "right": 70}]},
    "position": {"direction": "long", "size": "full"},
    "risk": None,
}

_RSI_ONLY_IR = {
    "asset": {"ticker": "TEST", "asset_class": "equity"},
    "indicators": [
        {"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}
    ],
    "entry": {"all_of": [{"left": "rsi14", "op": "<", "right": 30}]},
    "exit": {"any_of": [{"left": "rsi14", "op": ">", "right": 70}]},
    "position": {"direction": "long", "size": "full"},
    "risk": None,
}


def test_compound_ir_passes_schema():
    validate_ir(_COMPOUND_IR)


def test_compound_warmup_is_max_of_all_indicators():
    # SMA(200) has the longest lookback (200), so warmup should be 200
    warmup = compute_ir_warmup(_COMPOUND_IR)
    assert warmup == 200


def test_compound_entry_signals_are_subset_of_rsi_alone():
    """AND semantics: compound entry ⊆ RSI-alone entry (bitwise subset check).

    Uses n=400 so that SMA(200) has enough bars to produce a defined series
    and the oscillating series generates RSI<30 crossings within the
    post-warmup window.
    """
    close = _oscillating_close(n=400)
    price_data = _price_data(close)

    # Full-series signals (not trimmed) so we can compare bar-by-bar
    compound_entries, _ = interpret_ir(_COMPOUND_IR, price_data)
    rsi_entries, _ = interpret_ir(_RSI_ONLY_IR, price_data)

    # Wherever compound fires, RSI-alone must also fire (AND ⊆ first operand)
    spurious = compound_entries & ~rsi_entries
    assert spurious.sum() == 0, (
        f"Compound entry fired on {spurious.sum()} bars where RSI-alone did not — "
        "AND semantics violated."
    )


def test_compound_strategy_runs_end_to_end():
    """Compound IR run through run_ir_backtest should not raise and return valid metrics."""
    close = _oscillating_close(n=400)
    price_data = _price_data(close)

    result = run_ir_backtest(_COMPOUND_IR, price_data, fees=0.0, slippage=0.0)

    assert isinstance(result.total_return, float)
    assert isinstance(result.num_trades, int)
    assert result.num_trades >= 0
    assert result.start < result.end


# ---------------------------------------------------------------------------
# 5. Misc interpreter correctness
# ---------------------------------------------------------------------------


def test_price_field_operand_resolves_to_close_series():
    """Operand 'close' in a condition should refer to the Close price column."""
    # Oscillating series ranges [80, 100]: use thresholds well inside that range.
    ir = {
        **RSI14_SPY_IR,
        "indicators": [],
        "entry": {"all_of": [{"left": "close", "op": ">", "right": 95}]},
        "exit": {"all_of": [{"left": "close", "op": "<", "right": 85}]},
    }
    close = _oscillating_close()
    price_data = _price_data(close)
    entries, exits = interpret_ir(ir, price_data)
    assert entries.any()
    assert exits.any()


def test_crosses_above_fires_only_on_transition():
    """crosses_above should be True only on the bar of the upward crossing."""
    idx = pd.date_range("2020-01-01", periods=6, freq="D")
    # Series: 10, 20, 30, 40, 50, 40 — it crosses above 25 on bar 2 only.
    close = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0, 40.0], index=idx)
    price_data = _price_data(close)

    ir = {
        "asset": {"ticker": "X", "asset_class": "equity"},
        "indicators": [],
        "entry": {"all_of": [{"left": "close", "op": "crosses_above", "right": 25}]},
        "exit": {"all_of": [{"left": "close", "op": "<", "right": 5}]},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }
    entries, _ = interpret_ir(ir, price_data)
    # Raw crossing happens at bar 2 (close goes from 20 to 30, crossing 25).
    # After the no-lookahead shift: entry fires at bar 3.
    assert entries.iloc[3] is np.bool_(True)
    # No other entry bars (only one crossing of 25 from below)
    assert entries.sum() == 1
