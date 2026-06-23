"""Plain-English verdict: map the four robustness checks (sensitivity,
deflated Sharpe, walk-forward, regime) onto one of four states, with
reasons drawn from the checks rather than raw numbers leading.

States (exactly one, never more, never fewer):
  - PASS            no material red flag from any check.
  - SHAKY            one or more caution signals, none severe enough alone
                      to call the strategy overfit.
  - LIKELY_OVERFIT   a confidence-bearing overfitting signature (walk-forward
                      degradation on folds with enough trades to trust, and/or
                      a deflated Sharpe that fails the multiple-testing bar).
  - UNTESTABLE       the walk-forward evidence needed to judge degradation is
                      itself too thin (mostly/entirely low_confidence folds)
                      to support ANY verdict about generalization -- reported
                      separately from LIKELY_OVERFIT on purpose, see below.

CRITICAL distinction this module exists to enforce: "we tested it and it's
overfit" (LIKELY_OVERFIT) is a different, stronger claim than "we don't have
enough evidence to test it at all" (UNTESTABLE). Walk-forward can come back
with every fold trading only a handful of in-sample trades; a sign-flip in
that situation (positive IS Sharpe -> negative OOS Sharpe) LOOKS like the
textbook overfitting signature but is built on noise, not a real degradation
measurement. Before any degradation reading is allowed to drive LIKELY_OVERFIT,
this module checks whether the walk-forward evidence is confidence-bearing
(see `LOW_CONFIDENCE_FOLD_SHARE_THRESHOLD`) and routes to UNTESTABLE instead
if it isn't -- regardless of how dramatic the raw degradation number looks.

A separate, structurally distinct no-exit case (`is_no_exit_strategy` /
`build_no_exit_result`) is NOT one of the four states above: a strategy with
no exit rule is buy-and-hold from its first entry, one open trade, nothing
for walk-forward/sensitivity/the DSR trial framing to act on. Running normal
verdict logic on it and dressing up the result as a strategy assessment would
misrepresent what was actually tested, so it short-circuits to a distinct
buy-and-hold comparison message instead. Callers (the `robustness.py`
orchestrator) MUST check `is_no_exit_strategy` before calling `compute_verdict`
or any of the round-trip checks at all.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from app.engine.backtest import compute_buy_and_hold_metrics, run_ir_backtest, run_ir_backtest_returns
from app.robustness.regime import RegimeReport
from app.robustness.sensitivity import ParamSensitivity
from app.robustness.walk_forward import WalkForwardResult
from app.translation.defaults import SEVERITY_WARNING, Assumption

PASS = "PASS"
SHAKY = "SHAKY"
LIKELY_OVERFIT = "LIKELY_OVERFIT"
UNTESTABLE = "UNTESTABLE"

# Bailey & Lopez de Prado frame DSR/PSR as a one-sided significance
# probability. 0.95 (the conventional "statistically significant" bar) is a
# strong pass; below 0.5 means the deflated, multiple-testing-adjusted
# Sharpe doesn't even clear a coin flip -- ours, documented, not from a
# specific recommended-cutoff passage in the papers.
DSR_STRONG_PASS_THRESHOLD = 0.95
DSR_FAIL_THRESHOLD = 0.5

# Sharpe-unit drop (aggregate IS - aggregate OOS) large enough to call a
# "confidence-bearing" degradation by itself, independent of a sign flip.
# Heuristic, ours: 0.5 Sharpe is a large swing on the same annualization
# convention this codebase uses everywhere else (TRADING_DAYS_PER_YEAR=252).
WF_DEGRADATION_THRESHOLD = 0.5

# If this share (or more) of walk-forward folds are individually
# low_confidence (chosen IS trade count below walk_forward.py's
# min_trades_for_confidence), the AGGREGATE IS/OOS Sharpe and the
# degradation computed from it are themselves built mostly out of noisy
# per-fold parameter choices -- not reliable enough to read as "the
# strategy generalizes" OR "the strategy is overfit." Half is the natural
# cut: at that point most of what the aggregate reflects is unreliable.
LOW_CONFIDENCE_FOLD_SHARE_THRESHOLD = 0.5


@dataclass(frozen=True)
class VerdictResult:
    verdict: str  # PASS | SHAKY | LIKELY_OVERFIT | UNTESTABLE
    reasons: tuple
    details: dict


@dataclass(frozen=True)
class NoExitResult:
    """Distinct from VerdictResult on purpose -- see module docstring. Never
    carries one of the four verdict states."""

    message: str
    first_entry_date: str | None
    strategy_metrics: dict | None
    benchmark_metrics: dict | None


def is_no_exit_strategy(assumptions: list[Assumption]) -> bool:
    """True if defaulting silently turned this strategy into buy-and-hold-
    from-first-entry (the SEVERITY_WARNING no-exit assumption)."""
    return any(a.field == "exit" and a.severity == SEVERITY_WARNING for a in assumptions)


def build_no_exit_result(
    ir: dict,
    price_data: pd.DataFrame,
    *,
    fees: float = 0.0,
    slippage: float = 0.0005,
) -> NoExitResult:
    """Buy-and-hold benchmark comparison for a no-exit strategy. Caller is
    responsible for checking `is_no_exit_strategy` first -- this function
    does not re-check the assumptions list."""
    daily_returns, eff_entries = run_ir_backtest_returns(ir, price_data, fees=fees, slippage=slippage)
    entry_dates = eff_entries[eff_entries].index

    if len(entry_dates) == 0:
        return NoExitResult(
            message="No exit rule, and the entry condition never fired either -- "
            "there is nothing to benchmark; this strategy never took a position.",
            first_entry_date=None,
            strategy_metrics=None,
            benchmark_metrics=None,
        )

    first_entry_date = entry_dates[0]
    strategy_result = run_ir_backtest(ir, price_data, fees=fees, slippage=slippage)
    bench_close = price_data["Close"].loc[first_entry_date:]
    benchmark_result = compute_buy_and_hold_metrics(bench_close, warmup=0, fees=fees, slippage=slippage)

    message = (
        "This isn't a round-trip strategy — with no exit rule it's buy-and-hold from "
        f"{first_entry_date.date()}. Robustness checks for round-trip strategies don't "
        "apply; here's the buy-and-hold benchmark comparison instead."
    )
    return NoExitResult(
        message=message,
        first_entry_date=str(first_entry_date.date()),
        strategy_metrics=strategy_result.as_dict(),
        benchmark_metrics=benchmark_result.as_dict(),
    )


def compute_verdict(
    *,
    walk_forward: WalkForwardResult,
    sensitivity: list[ParamSensitivity],
    dsr: dict,
    regime: RegimeReport,
) -> VerdictResult:
    """Map the four round-trip robustness checks to one verdict. Must not be
    called on a no-exit strategy -- check `is_no_exit_strategy` first."""
    folds = walk_forward.folds
    total_folds = len(folds)
    low_confidence_folds = sum(1 for f in folds if f.low_confidence)
    low_confidence_share = (low_confidence_folds / total_folds) if total_folds else None

    is_sharpe = walk_forward.aggregate_is_sharpe
    oos_sharpe = walk_forward.aggregate_oos_sharpe
    degradation = walk_forward.degradation
    has_wf_signal = not (math.isnan(is_sharpe) or math.isnan(oos_sharpe))
    sign_flip = has_wf_signal and is_sharpe > 0 and oos_sharpe < 0
    large_degradation = has_wf_signal and not math.isnan(degradation) and degradation >= WF_DEGRADATION_THRESHOLD
    wf_overfit_signature = sign_flip or large_degradation

    wf_evidence_thin = total_folds == 0 or (
        low_confidence_share is not None and low_confidence_share >= LOW_CONFIDENCE_FOLD_SHARE_THRESHOLD
    )

    dsr_value = dsr.get("dsr", float("nan")) if dsr else float("nan")
    dsr_fails = not math.isnan(dsr_value) and dsr_value < DSR_FAIL_THRESHOLD
    dsr_strong_pass = not math.isnan(dsr_value) and dsr_value >= DSR_STRONG_PASS_THRESHOLD
    dsr_marginal = not math.isnan(dsr_value) and not dsr_fails and not dsr_strong_pass

    fragile_params = [s.param_id for s in sensitivity if s.robustness_label == "fragile (sharp peak)"]

    regime_flags = []
    if regime.concentrated_regime is not None:
        regime_flags.append(
            f"{regime.concentration_share:.0%} of gains came from a single regime "
            f"({regime.concentrated_regime})"
        )
    for flag in regime.marginal_flags:
        regime_flags.append(f"{flag.share:.0%} of gains are {flag.dependence_label}")

    details = {
        "total_folds": total_folds,
        "low_confidence_folds": low_confidence_folds,
        "low_confidence_fold_share": low_confidence_share,
        "aggregate_is_sharpe": is_sharpe,
        "aggregate_oos_sharpe": oos_sharpe,
        "walk_forward_degradation": degradation,
        "dsr": dsr_value,
        "fragile_params": fragile_params,
        "regime_flags": regime_flags,
    }

    # The untestable short-circuit: an apparent overfit signature built
    # entirely (or mostly) out of folds too thin to trust. Checked BEFORE
    # any other signal so a fragile param or a bad DSR can't pull this back
    # toward LIKELY_OVERFIT -- the WF evidence problem applies regardless.
    if wf_overfit_signature and wf_evidence_thin:
        reasons = (
            f"Out-of-sample performance looks worse than in-sample, but "
            f"{low_confidence_folds}/{total_folds} walk-forward folds had too few "
            "in-sample trades to trust the parameters that degradation was measured "
            "against -- there isn't enough evidence here to call this overfit, only "
            "that it hasn't been validated.",
        )
        return VerdictResult(verdict=UNTESTABLE, reasons=reasons, details=details)

    if total_folds == 0:
        reasons = (
            "Walk-forward validation could not run at all (not enough price history "
            "for a single in-sample/out-of-sample fold) -- there isn't enough evidence "
            "to validate this strategy's generalization.",
        )
        return VerdictResult(verdict=UNTESTABLE, reasons=reasons, details=details)

    strong_overfit_signal = (wf_overfit_signature and not wf_evidence_thin) or dsr_fails
    if strong_overfit_signal:
        reasons = []
        if wf_overfit_signature and not wf_evidence_thin:
            reasons.append(
                f"Out-of-sample Sharpe degraded sharply vs in-sample (IS {is_sharpe:.2f} -> "
                f"OOS {oos_sharpe:.2f}) across folds with enough trades to trust."
            )
        if dsr_fails:
            reasons.append(
                f"Deflated Sharpe Ratio ({dsr_value:.2f}) is below the bar once corrected "
                "for the number of configurations tried."
            )
        if fragile_params:
            reasons.append(f"Performance is also highly sensitive to exact parameter values: {', '.join(fragile_params)}.")
        if regime_flags:
            reasons.append("Also: " + "; ".join(regime_flags) + ".")
        return VerdictResult(verdict=LIKELY_OVERFIT, reasons=tuple(reasons), details=details)

    caution_reasons = []
    if wf_evidence_thin:
        caution_reasons.append(
            f"Walk-forward evidence is thin ({low_confidence_folds}/{total_folds} folds "
            "low_confidence) -- treat any pass/fail read with caution."
        )
    elif not math.isnan(degradation) and degradation > 0:
        caution_reasons.append(
            f"Mild out-of-sample degradation (IS {is_sharpe:.2f} -> OOS {oos_sharpe:.2f})."
        )
    if dsr_marginal:
        caution_reasons.append(
            f"Deflated Sharpe Ratio ({dsr_value:.2f}) is positive but not strongly above "
            "the multiple-testing bar."
        )
    if fragile_params:
        caution_reasons.append(f"Performance is sensitive to exact parameter values: {', '.join(fragile_params)}.")
    if regime_flags:
        caution_reasons.append("; ".join(regime_flags) + ".")

    if caution_reasons:
        return VerdictResult(verdict=SHAKY, reasons=tuple(caution_reasons), details=details)

    reasons = (
        "Walk-forward, parameter sensitivity, deflated Sharpe, and regime checks found "
        "no material red flags.",
    )
    return VerdictResult(verdict=PASS, reasons=reasons, details=details)
