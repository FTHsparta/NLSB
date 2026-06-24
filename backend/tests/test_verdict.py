import math

import numpy as np
import pandas as pd

from app.robustness import verdict as verdict_module
from app.robustness.regime import MarginalConcentration, RegimeReport
from app.robustness.sensitivity import GridPointResult, ParamSensitivity
from app.robustness.verdict import (
    LIKELY_OVERFIT,
    PASS,
    SHAKY,
    UNTESTABLE,
    build_no_exit_result,
    compute_verdict,
    is_no_exit_strategy,
)
from app.robustness.walk_forward import FoldResult, WalkForwardResult
from app.translation.defaults import Assumption, SEVERITY_NOTE, SEVERITY_WARNING, apply_defaults

# ---------------------------------------------------------------------------
# Fixture builders -- crafted dataclasses for precise control, matching the
# style 4a/4b already used (monkeypatched/crafted inputs over guessing what
# a real backtest happens to produce).
# ---------------------------------------------------------------------------


def _fold(fold_index, is_sharpe, is_trades, oos_sharpe, low_confidence=False):
    return FoldResult(
        fold_index=fold_index,
        is_start="2020-01-01",
        is_end="2020-06-01",
        oos_start="2020-06-02",
        oos_end="2020-12-01",
        chosen_params={},
        is_sharpe=is_sharpe,
        is_total_return=0.1,
        is_num_trades=is_trades,
        oos_sharpe=oos_sharpe,
        oos_total_return=0.0,
        oos_num_trades=5,
        low_confidence=low_confidence,
    )


def _wf(folds, agg_is, agg_oos, degradation):
    return WalkForwardResult(folds=tuple(folds), aggregate_is_sharpe=agg_is, aggregate_oos_sharpe=agg_oos, degradation=degradation)


def _empty_regime():
    return RegimeReport(breakdowns=(), concentrated_regime=None, concentration_share=None, marginal_flags=())


def _dsr(value):
    return {"n_trials": 5, "var_sr_trials": 0.01, "sr0": 0.1, "dsr": value}


# ---------------------------------------------------------------------------
# INVARIANT 2: degradation built entirely from low_confidence folds -> UNTESTABLE
# ---------------------------------------------------------------------------


def test_invariant2_untestable_when_degradation_is_all_low_confidence_folds():
    folds = [
        _fold(0, is_sharpe=1.5, is_trades=3, oos_sharpe=-1.0, low_confidence=True),
        _fold(1, is_sharpe=1.2, is_trades=2, oos_sharpe=-0.8, low_confidence=True),
    ]
    wf = _wf(folds, agg_is=1.35, agg_oos=-0.9, degradation=2.25)

    result = compute_verdict(walk_forward=wf, sensitivity=[], dsr=_dsr(0.97), regime=_empty_regime())

    assert result.verdict == UNTESTABLE
    assert result.verdict != LIKELY_OVERFIT


def test_invariant2_majority_low_confidence_share_also_routes_untestable():
    """Not literally every fold, but enough (>= the documented threshold)
    that the aggregate degradation can't be trusted."""
    folds = [
        _fold(0, 1.5, 3, -1.0, low_confidence=True),
        _fold(1, 1.2, 2, -0.8, low_confidence=True),
        _fold(2, 0.9, 25, -0.7, low_confidence=False),
    ]
    wf = _wf(folds, agg_is=1.2, agg_oos=-0.83, degradation=2.03)

    result = compute_verdict(walk_forward=wf, sensitivity=[], dsr=_dsr(0.97), regime=_empty_regime())

    assert result.verdict == UNTESTABLE


# ---------------------------------------------------------------------------
# INVARIANT 3: confidence-bearing folds AND clear degradation -> LIKELY_OVERFIT
# (proves the two paths are actually distinguished)
# ---------------------------------------------------------------------------


def test_invariant3_likely_overfit_when_folds_are_confidence_bearing():
    folds = [
        _fold(0, is_sharpe=1.5, is_trades=20, oos_sharpe=-1.0, low_confidence=False),
        _fold(1, is_sharpe=1.2, is_trades=15, oos_sharpe=-0.8, low_confidence=False),
    ]
    wf = _wf(folds, agg_is=1.35, agg_oos=-0.9, degradation=2.25)

    result = compute_verdict(walk_forward=wf, sensitivity=[], dsr=_dsr(0.97), regime=_empty_regime())

    assert result.verdict == LIKELY_OVERFIT
    assert result.verdict != UNTESTABLE


def test_low_confidence_share_below_threshold_does_not_block_overfit_verdict():
    """1 of 4 folds low_confidence (25%, below the 50% threshold) must not
    suppress a real, mostly-trustworthy degradation signature."""
    folds = [
        _fold(0, 1.5, 20, -1.0, low_confidence=False),
        _fold(1, 1.4, 18, -0.9, low_confidence=False),
        _fold(2, 1.3, 22, -1.1, low_confidence=False),
        _fold(3, 1.2, 3, -0.8, low_confidence=True),
    ]
    wf = _wf(folds, agg_is=1.35, agg_oos=-0.95, degradation=2.3)

    result = compute_verdict(walk_forward=wf, sensitivity=[], dsr=_dsr(0.97), regime=_empty_regime())

    assert result.verdict == LIKELY_OVERFIT


# ---------------------------------------------------------------------------
# Other verdict paths
# ---------------------------------------------------------------------------


def test_pass_when_no_check_raises_a_flag():
    folds = [_fold(0, 0.5, 20, 0.6, low_confidence=False)]
    wf = _wf(folds, agg_is=0.5, agg_oos=0.6, degradation=-0.1)

    result = compute_verdict(walk_forward=wf, sensitivity=[], dsr=_dsr(0.97), regime=_empty_regime())

    assert result.verdict == PASS


def test_shaky_from_fragile_sensitivity_param():
    folds = [_fold(0, 0.5, 20, 0.6, low_confidence=False)]
    wf = _wf(folds, agg_is=0.5, agg_oos=0.6, degradation=-0.1)
    fragile = ParamSensitivity(
        param_id="indicators.rsi14.period",
        kind="period",
        stated_value=14,
        grid_points=(GridPointResult(value=14, sharpe_ratio=1.0, per_period_sharpe_ratio=0.06, total_return=0.1, num_trades=5),),
        peakiness=1.5,
        robustness_label="fragile (sharp peak)",
    )

    result = compute_verdict(walk_forward=wf, sensitivity=[fragile], dsr=_dsr(0.97), regime=_empty_regime())

    assert result.verdict == SHAKY
    assert any("sensitive" in r for r in result.reasons)


def test_shaky_from_regime_marginal_flag():
    folds = [_fold(0, 0.5, 20, 0.6, low_confidence=False)]
    wf = _wf(folds, agg_is=0.5, agg_oos=0.6, degradation=-0.1)
    regime = RegimeReport(
        breakdowns=(),
        concentrated_regime=None,
        concentration_share=None,
        marginal_flags=(MarginalConcentration(axis="trend", dominant_label="bull", share=0.95),),
    )

    result = compute_verdict(walk_forward=wf, sensitivity=[], dsr=_dsr(0.97), regime=regime)

    assert result.verdict == SHAKY
    assert any("bull-dependent" in r for r in result.reasons)


def test_likely_overfit_from_dsr_alone():
    folds = [_fold(0, 0.5, 20, 0.55, low_confidence=False), _fold(1, 0.4, 18, 0.45, low_confidence=False)]
    wf = _wf(folds, agg_is=0.45, agg_oos=0.5, degradation=-0.05)

    result = compute_verdict(walk_forward=wf, sensitivity=[], dsr=_dsr(0.3), regime=_empty_regime())

    assert result.verdict == LIKELY_OVERFIT
    assert any("Deflated Sharpe" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# Phase 4c calibration fixes
# ---------------------------------------------------------------------------


def test_calibration_invariant1_thin_folds_plus_failing_dsr_is_untestable_not_overfit():
    """A DSR-fail must not manufacture a confident LIKELY_OVERFIT out of
    higher moments estimated on a thin-trade return series -- same
    underlying problem the WF axis already guards against."""
    folds = [
        _fold(0, is_sharpe=0.2, is_trades=3, oos_sharpe=0.1, low_confidence=True),
        _fold(1, is_sharpe=0.1, is_trades=2, oos_sharpe=0.05, low_confidence=True),
    ]
    wf = _wf(folds, agg_is=0.15, agg_oos=0.075, degradation=0.075)  # no WF overfit signature

    result = compute_verdict(walk_forward=wf, sensitivity=[], dsr=_dsr(0.3), regime=_empty_regime())

    assert result.verdict == UNTESTABLE
    assert result.verdict != LIKELY_OVERFIT
    assert any("Deflated Sharpe" in r for r in result.reasons)


def test_calibration_invariant2_confidence_bearing_folds_plus_failing_dsr_still_overfit():
    """Guard against over-correcting: the untestable override only applies
    on the untestable axis -- a failing DSR with trustworthy WF evidence
    must still drive LIKELY_OVERFIT."""
    folds = [
        _fold(0, is_sharpe=0.5, is_trades=20, oos_sharpe=0.55, low_confidence=False),
        _fold(1, is_sharpe=0.4, is_trades=18, oos_sharpe=0.45, low_confidence=False),
    ]
    wf = _wf(folds, agg_is=0.45, agg_oos=0.5, degradation=-0.05)  # no WF overfit signature

    result = compute_verdict(walk_forward=wf, sensitivity=[], dsr=_dsr(0.3), regime=_empty_regime())

    assert result.verdict == LIKELY_OVERFIT


def test_calibration_invariant3_large_drop_landing_strongly_positive_is_not_overfit():
    """IS 3.0 -> OOS 2.4: a 0.6-Sharpe haircut on a still-excellent OOS
    number is not, on its own, the overfit tell."""
    folds = [
        _fold(0, is_sharpe=3.1, is_trades=30, oos_sharpe=2.5, low_confidence=False),
        _fold(1, is_sharpe=2.9, is_trades=28, oos_sharpe=2.3, low_confidence=False),
    ]
    wf = _wf(folds, agg_is=3.0, agg_oos=2.4, degradation=0.6)

    result = compute_verdict(walk_forward=wf, sensitivity=[], dsr=_dsr(0.97), regime=_empty_regime())

    assert result.verdict != LIKELY_OVERFIT


def test_calibration_invariant4_sign_flip_into_loss_is_still_overfit():
    """IS 0.4 -> OOS -0.2: a sign flip into loss is still the tell, even
    though the raw drop (0.6) is the same size as invariant 3's."""
    folds = [
        _fold(0, is_sharpe=0.45, is_trades=30, oos_sharpe=-0.25, low_confidence=False),
        _fold(1, is_sharpe=0.35, is_trades=28, oos_sharpe=-0.15, low_confidence=False),
    ]
    wf = _wf(folds, agg_is=0.4, agg_oos=-0.2, degradation=0.6)

    result = compute_verdict(walk_forward=wf, sensitivity=[], dsr=_dsr(0.97), regime=_empty_regime())

    assert result.verdict == LIKELY_OVERFIT


def test_large_drop_landing_strongly_positive_still_contributes_to_shaky():
    """Not damning on its own (invariant 3), but still worth a caution."""
    folds = [
        _fold(0, is_sharpe=3.1, is_trades=30, oos_sharpe=2.5, low_confidence=False),
        _fold(1, is_sharpe=2.9, is_trades=28, oos_sharpe=2.3, low_confidence=False),
    ]
    wf = _wf(folds, agg_is=3.0, agg_oos=2.4, degradation=0.6)

    result = compute_verdict(walk_forward=wf, sensitivity=[], dsr=_dsr(0.97), regime=_empty_regime())

    assert result.verdict == SHAKY
    assert any("degradation" in r.lower() for r in result.reasons)


def test_untestable_when_no_folds_completed_at_all():
    wf = WalkForwardResult(folds=(), aggregate_is_sharpe=float("nan"), aggregate_oos_sharpe=float("nan"), degradation=float("nan"))

    result = compute_verdict(walk_forward=wf, sensitivity=[], dsr=_dsr(0.97), regime=_empty_regime())

    assert result.verdict == UNTESTABLE


# ---------------------------------------------------------------------------
# INVARIANT 4 + no-exit short-circuit (verdict.py building blocks)
# ---------------------------------------------------------------------------


def test_is_no_exit_strategy_true_for_the_warning_severity_exit_assumption():
    sparse_ir = {
        "asset": {"ticker": "SPY"},
        "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
    }
    _full_ir, assumptions = apply_defaults(sparse_ir)
    assert is_no_exit_strategy(assumptions)


def test_is_no_exit_strategy_false_when_exit_is_stated():
    sparse_ir = {
        "asset": {"ticker": "SPY"},
        "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        "exit": {"left": "rsi14", "op": ">", "right": 70},
    }
    _full_ir, assumptions = apply_defaults(sparse_ir)
    assert not is_no_exit_strategy(assumptions)


def test_is_no_exit_strategy_ignores_note_severity_assumptions():
    assumptions = [Assumption(field="asset.asset_class", value="equity", reason="defaulted", severity=SEVERITY_NOTE)]
    assert not is_no_exit_strategy(assumptions)


def _oscillating_close(n: int = 200) -> pd.Series:
    block = np.concatenate([-np.ones(20), np.ones(20)])
    reps = int(np.ceil((n - 1) / len(block)))
    deltas = np.tile(block, reps)[: n - 1]
    close = 100 + np.concatenate([[0], np.cumsum(deltas)])
    idx = pd.date_range("2015-01-01", periods=n, freq="D")
    return pd.Series(close, index=idx, dtype=float)


def _price_data(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close})


def test_invariant4_no_exit_result_never_carries_a_verdict_state():
    sparse_ir = {
        "asset": {"ticker": "SPY"},
        "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
    }
    full_ir, _assumptions = apply_defaults(sparse_ir)
    price_data = _price_data(_oscillating_close())

    result = build_no_exit_result(full_ir, price_data, fees=0.0, slippage=0.0)

    for verdict_state in (PASS, SHAKY, LIKELY_OVERFIT, UNTESTABLE):
        assert result.message != verdict_state
    assert not hasattr(result, "verdict")
    assert "buy-and-hold" in result.message
    assert result.first_entry_date is not None
    assert not math.isnan(result.strategy_metrics["total_return"])
    assert not math.isnan(result.benchmark_metrics["total_return"])


def test_no_exit_result_handles_an_entry_that_never_fires():
    sparse_ir = {
        "asset": {"ticker": "SPY"},
        "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}}],
        # threshold an oscillating RSI(14) series will never satisfy
        "entry": {"left": "rsi14", "op": "<", "right": -1},
    }
    full_ir, _assumptions = apply_defaults(sparse_ir)
    price_data = _price_data(_oscillating_close())

    result = build_no_exit_result(full_ir, price_data, fees=0.0, slippage=0.0)

    assert result.first_entry_date is None
    assert result.strategy_metrics is None
    assert result.benchmark_metrics is None
