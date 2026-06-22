"""Rolling in-sample / out-of-sample walk-forward validation.

For each fold: search the parameter grid (from `params.py`) on an
in-sample (IS) window, freeze the winning configuration, and test it on
the immediately-following out-of-sample (OOS) window. Step forward and
repeat. Every backtest -- in-sample search and out-of-sample test alike --
goes through `run_ir_backtest`; this module never reimplements backtest
math, only slices `price_data` and mutates the IR's tunable values.

Large OOS degradation relative to IS performance is the classic overfitting
signature: the chosen parameters fit the in-sample noise rather than a
real, persistent edge.

Window defaults (bars, not calendar time, to keep folds exact regardless of
weekends/holidays): IS=756 bars (~3 trading years), OOS=252 bars (~1 year),
step=252 bars (~1 year) -- a reasonable default for a strategy backtested
over a decade-plus of daily bars. All three are caller-configurable.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import pandas as pd

from app.engine.backtest import run_ir_backtest
from app.robustness.params import TunableParam, extract_tunable_params, set_in_copy

DEFAULT_IN_SAMPLE_BARS = 756
DEFAULT_OUT_OF_SAMPLE_BARS = 252
DEFAULT_STEP_BARS = 252

# Below this many in-sample trades, the IS Sharpe used to pick parameters is
# noisy enough that "optimizing" it is itself a form of overfitting. Surfaced
# per fold so 4c's verdict layer can flag low-confidence folds; not acted on
# here.
DEFAULT_MIN_TRADES_FOR_CONFIDENCE = 10

RETAIL_FEES = 0.0
RETAIL_SLIPPAGE = 0.0005


@dataclass(frozen=True)
class FoldResult:
    fold_index: int
    is_start: str
    is_end: str
    oos_start: str
    oos_end: str
    chosen_params: dict
    is_sharpe: float
    is_total_return: float
    is_num_trades: int
    oos_sharpe: float
    oos_total_return: float
    oos_num_trades: int
    low_confidence: bool
    error: str | None = None


@dataclass(frozen=True)
class WalkForwardResult:
    folds: tuple
    aggregate_is_sharpe: float
    aggregate_oos_sharpe: float
    degradation: float  # aggregate_is_sharpe - aggregate_oos_sharpe


def run_walk_forward(
    ir: dict,
    price_data: pd.DataFrame,
    *,
    in_sample_bars: int = DEFAULT_IN_SAMPLE_BARS,
    out_of_sample_bars: int = DEFAULT_OUT_OF_SAMPLE_BARS,
    step_bars: int = DEFAULT_STEP_BARS,
    fees: float = RETAIL_FEES,
    slippage: float = RETAIL_SLIPPAGE,
    min_trades_for_confidence: int = DEFAULT_MIN_TRADES_FOR_CONFIDENCE,
) -> WalkForwardResult:
    tunables = extract_tunable_params(ir)
    candidates = _candidate_configs(tunables)

    folds: list[FoldResult] = []
    fold_index = 0
    start = 0
    n = len(price_data)
    while start + in_sample_bars + out_of_sample_bars <= n:
        is_slice = price_data.iloc[start : start + in_sample_bars]
        oos_slice = price_data.iloc[
            start + in_sample_bars : start + in_sample_bars + out_of_sample_bars
        ]
        folds.append(
            _run_fold(
                fold_index,
                ir,
                tunables,
                candidates,
                is_slice,
                oos_slice,
                fees,
                slippage,
                min_trades_for_confidence,
            )
        )
        fold_index += 1
        start += step_bars

    is_sharpes = [f.is_sharpe for f in folds if not math.isnan(f.is_sharpe)]
    oos_sharpes = [f.oos_sharpe for f in folds if not math.isnan(f.oos_sharpe)]
    agg_is = sum(is_sharpes) / len(is_sharpes) if is_sharpes else float("nan")
    agg_oos = sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else float("nan")
    degradation = (
        agg_is - agg_oos if not (math.isnan(agg_is) or math.isnan(agg_oos)) else float("nan")
    )

    return WalkForwardResult(
        folds=tuple(folds),
        aggregate_is_sharpe=agg_is,
        aggregate_oos_sharpe=agg_oos,
        degradation=degradation,
    )


def _run_fold(
    fold_index: int,
    ir: dict,
    tunables: list[TunableParam],
    candidates: list[dict],
    is_slice: pd.DataFrame,
    oos_slice: pd.DataFrame,
    fees: float,
    slippage: float,
    min_trades_for_confidence: int,
) -> FoldResult:
    is_start = str(is_slice.index[0].date())
    is_end = str(is_slice.index[-1].date())
    oos_start = str(oos_slice.index[0].date())
    oos_end = str(oos_slice.index[-1].date())

    stated_values = {t.param_id: t.value for t in tunables}
    scored = []
    for candidate in candidates:
        mutated_ir = _apply_candidate(ir, tunables, candidate)
        try:
            result = run_ir_backtest(mutated_ir, is_slice, fees=fees, slippage=slippage)
            sharpe = result.sharpe_ratio
            num_trades = result.num_trades
            total_return = result.total_return
            error = None
        except Exception as exc:  # noqa: BLE001 -- one bad candidate must not abort the fold
            sharpe = float("nan")
            num_trades = 0
            total_return = float("nan")
            error = str(exc)
        scored.append((candidate, sharpe, num_trades, total_return, error))

    chosen = _select_best(scored, stated_values, tunables)
    chosen_candidate, chosen_sharpe, chosen_is_trades, chosen_is_return, chosen_error = chosen

    if chosen_error is not None:
        return FoldResult(
            fold_index=fold_index,
            is_start=is_start,
            is_end=is_end,
            oos_start=oos_start,
            oos_end=oos_end,
            chosen_params=chosen_candidate,
            is_sharpe=float("nan"),
            is_total_return=float("nan"),
            is_num_trades=0,
            oos_sharpe=float("nan"),
            oos_total_return=float("nan"),
            oos_num_trades=0,
            low_confidence=True,
            error=chosen_error,
        )

    frozen_ir = _apply_candidate(ir, tunables, chosen_candidate)
    try:
        oos_result = run_ir_backtest(frozen_ir, oos_slice, fees=fees, slippage=slippage)
        oos_sharpe = oos_result.sharpe_ratio
        oos_trades = oos_result.num_trades
        oos_return = oos_result.total_return
        oos_error = None
    except Exception as exc:  # noqa: BLE001
        oos_sharpe = float("nan")
        oos_trades = 0
        oos_return = float("nan")
        oos_error = str(exc)

    return FoldResult(
        fold_index=fold_index,
        is_start=is_start,
        is_end=is_end,
        oos_start=oos_start,
        oos_end=oos_end,
        chosen_params=chosen_candidate,
        is_sharpe=chosen_sharpe,
        is_total_return=chosen_is_return,
        is_num_trades=chosen_is_trades,
        oos_sharpe=oos_sharpe,
        oos_total_return=oos_return,
        oos_num_trades=oos_trades,
        low_confidence=chosen_is_trades < min_trades_for_confidence,
        error=oos_error,
    )


def _candidate_configs(tunables: list[TunableParam]) -> list[dict]:
    if not tunables:
        return [{}]
    ids = [t.param_id for t in tunables]
    grids = [t.grid for t in tunables]
    return [dict(zip(ids, values)) for values in itertools.product(*grids)]


def _apply_candidate(ir: dict, tunables: list[TunableParam], candidate: dict) -> dict:
    mutated = ir
    for t in tunables:
        mutated = set_in_copy(mutated, t.path, candidate[t.param_id])
    return mutated


def _select_best(scored: list[tuple], stated_values: dict, tunables: list[TunableParam]) -> tuple:
    """Pick the candidate with the highest IS Sharpe. Ties broken
    deterministically: closest to the stated values, then smallest total
    magnitude (the "simpler" config), then canonical grid order -- so
    re-running the same fold always picks the same candidate."""

    def sort_key(item):
        candidate, sharpe, _num_trades, _total_return, error = item
        sharpe_key = sharpe if (error is None and not math.isnan(sharpe)) else float("-inf")
        distance_from_stated = sum(
            abs(candidate[t.param_id] - stated_values[t.param_id]) for t in tunables
        )
        magnitude = sum(abs(v) for v in candidate.values())
        canonical = tuple(candidate[t.param_id] for t in tunables)
        return (-sharpe_key, distance_from_stated, magnitude, canonical)

    return min(scored, key=sort_key)
