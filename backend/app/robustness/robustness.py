"""Orchestrator: run all four robustness checks (or the no-exit short-
circuit) and return one structured, JSON-serializable result the frontend
can render.

Branches on the no-exit signal (the SEVERITY_WARNING `exit` assumption from
`app.translation.defaults.apply_defaults`) BEFORE running any round-trip
machinery: walk-forward folds, one-at-a-time sensitivity sweeps, and the DSR
trial framing all assume a strategy with repeated entries/exits to
fold/sweep/count trials over -- none of that applies to a single open
buy-and-hold position, so the no-exit case short-circuits to a distinct
buy-and-hold benchmark message instead (see `app.robustness.verdict`'s
module docstring for why this is a separate result, never one of the four
verdict states).
"""

from __future__ import annotations

import dataclasses

import pandas as pd

from app.data.market_data import realized_window
from app.engine.backtest import run_ir_backtest_returns
from app.robustness.deflated_sharpe import deflated_sharpe_ratio_from_trials
from app.robustness.regime import run_regime_analysis
from app.robustness.sensitivity import run_sensitivity
from app.robustness.verdict import build_no_exit_result, compute_verdict, is_no_exit_strategy
from app.robustness.walk_forward import (
    DEFAULT_IN_SAMPLE_BARS,
    DEFAULT_MIN_TRADES_FOR_CONFIDENCE,
    DEFAULT_OUT_OF_SAMPLE_BARS,
    DEFAULT_STEP_BARS,
    run_walk_forward,
)
from app.translation.defaults import Assumption

RETAIL_FEES = 0.0
RETAIL_SLIPPAGE = 0.0005

# Stable top-level keys of the dict `run_robustness` returns -- pinned in
# `test_robustness.py::test_result_schema_keys_are_stable` so a future
# refactor can't silently rename/drop a key the frontend depends on.
#
# `window` (Phase 12B) is present on EVERY result, unconditionally, including
# the no-exit and untestable paths. It is not a diagnostic that appears when
# something is wrong: a correct run reports the window it judged too, because
# a reader should not have to suspect a problem before being told which data
# produced the answer. One nested key keeps the top level flat.
RESULT_KEYS = (
    "kind",
    "no_exit",
    "sensitivity",
    "walk_forward",
    "deflated_sharpe",
    "regime",
    "verdict",
    "window",
)


def run_robustness(
    ir: dict,
    price_data: pd.DataFrame,
    assumptions: list[Assumption],
    *,
    fees: float = RETAIL_FEES,
    slippage: float = RETAIL_SLIPPAGE,
    in_sample_bars: int = DEFAULT_IN_SAMPLE_BARS,
    out_of_sample_bars: int = DEFAULT_OUT_OF_SAMPLE_BARS,
    step_bars: int = DEFAULT_STEP_BARS,
    min_trades_for_confidence: int = DEFAULT_MIN_TRADES_FOR_CONFIDENCE,
    requested_start: object = None,
    requested_end: object = None,
) -> dict:
    """Run the full robustness suite, or the no-exit short-circuit.

    Returns a dict with exactly the keys in `RESULT_KEYS`. ``kind`` is
    ``"no_exit"`` or ``"full"`` and determines which of the other keys are
    populated (the rest are ``None``) -- callers should branch on ``kind``,
    not on which keys happen to be non-None.

    ``window`` is derived from `price_data`'s own index, so it describes the
    data this call actually ran on and cannot drift from it. The requested
    dates are optional and reported as None when a caller has none to give
    (the fixture dumper, direct unit tests); the HTTP path always supplies
    them.
    """
    window = realized_window(price_data, requested_start, requested_end)

    if is_no_exit_strategy(assumptions):
        no_exit = build_no_exit_result(ir, price_data, fees=fees, slippage=slippage)
        return {
            "kind": "no_exit",
            "no_exit": dataclasses.asdict(no_exit),
            "sensitivity": None,
            "walk_forward": None,
            "deflated_sharpe": None,
            "regime": None,
            "verdict": None,
            "window": window,
        }

    sensitivity = run_sensitivity(ir, price_data, fees=fees, slippage=slippage)
    walk_forward = run_walk_forward(
        ir,
        price_data,
        in_sample_bars=in_sample_bars,
        out_of_sample_bars=out_of_sample_bars,
        step_bars=step_bars,
        fees=fees,
        slippage=slippage,
        min_trades_for_confidence=min_trades_for_confidence,
    )
    regime = run_regime_analysis(ir, price_data, fees=fees, slippage=slippage)

    daily_returns, _eff_entries = run_ir_backtest_returns(ir, price_data, fees=fees, slippage=slippage)
    trial_sharpes = [
        grid_point.per_period_sharpe_ratio
        for param in sensitivity
        for grid_point in param.grid_points
        if grid_point.error is None and not pd.isna(grid_point.per_period_sharpe_ratio)
    ]
    dsr = deflated_sharpe_ratio_from_trials(daily_returns, trial_sharpes)

    verdict = compute_verdict(walk_forward=walk_forward, sensitivity=sensitivity, dsr=dsr, regime=regime)

    return {
        "kind": "full",
        "no_exit": None,
        "sensitivity": [dataclasses.asdict(s) for s in sensitivity],
        "walk_forward": dataclasses.asdict(walk_forward),
        "deflated_sharpe": dsr,
        "regime": dataclasses.asdict(regime),
        "verdict": dataclasses.asdict(verdict),
        "window": window,
    }
