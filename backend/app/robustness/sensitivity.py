"""One-at-a-time parameter sensitivity sweep.

For each tunable parameter (from `params.py`), re-run the strategy with that
parameter set to each value in its neighborhood grid, holding every other
parameter at its current IR value. Every sub-backtest goes through
`run_ir_backtest` -- this module never reimplements backtest math, and
never touches anything the LLM produced (it operates on an already-
validated full IR).

Peakiness/robustness scoring below is OUR heuristic (documented here, not
drawn from a specific paper): a sharp performance peak at the stated value
suggests the user's (or an optimizer's) choice was fit to this exact value;
a broad plateau suggests the strategy doesn't depend on hitting that value
precisely.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.engine.backtest import TRADING_DAYS_PER_YEAR, run_ir_backtest
from app.robustness.params import TunableParam, extract_tunable_params, set_in_copy

# Heuristic thresholds for `_robustness_label` -- ours, not from literature.
_ROBUST_PEAKINESS_MAX = 0.25
_FRAGILE_PEAKINESS_MIN = 0.75

_SQRT_TRADING_DAYS = math.sqrt(TRADING_DAYS_PER_YEAR)


@dataclass(frozen=True)
class GridPointResult:
    value: float
    sharpe_ratio: float
    per_period_sharpe_ratio: float
    total_return: float
    num_trades: int
    error: str | None = None


@dataclass(frozen=True)
class ParamSensitivity:
    param_id: str
    kind: str
    stated_value: float
    grid_points: tuple
    peakiness: float
    robustness_label: str


def run_sensitivity(
    ir: dict, price_data, *, fees: float = 0.0, slippage: float = 0.0005
) -> list[ParamSensitivity]:
    """Sweep every tunable parameter in *ir* and score its robustness."""
    return [
        _sweep_one(ir, price_data, tunable, fees, slippage)
        for tunable in extract_tunable_params(ir)
    ]


def _sweep_one(
    ir: dict, price_data, tunable: TunableParam, fees: float, slippage: float
) -> ParamSensitivity:
    points = []
    for value in tunable.grid:
        mutated_ir = set_in_copy(ir, tunable.path, value)
        try:
            result = run_ir_backtest(mutated_ir, price_data, fees=fees, slippage=slippage)
            points.append(
                GridPointResult(
                    value=value,
                    sharpe_ratio=result.sharpe_ratio,
                    per_period_sharpe_ratio=result.sharpe_ratio / _SQRT_TRADING_DAYS,
                    total_return=result.total_return,
                    num_trades=result.num_trades,
                )
            )
        except Exception as exc:  # noqa: BLE001 -- a bad grid point must not abort the sweep
            points.append(
                GridPointResult(
                    value=value,
                    sharpe_ratio=float("nan"),
                    per_period_sharpe_ratio=float("nan"),
                    total_return=float("nan"),
                    num_trades=0,
                    error=str(exc),
                )
            )

    peakiness = _peakiness(tunable.value, points)
    return ParamSensitivity(
        param_id=tunable.param_id,
        kind=tunable.kind,
        stated_value=tunable.value,
        grid_points=tuple(points),
        peakiness=peakiness,
        robustness_label=_robustness_label(peakiness),
    )


def _peakiness(stated_value: float, points: list[GridPointResult]) -> float:
    """Range of grid Sharpe ratios, normalized by the Sharpe at the stated
    value. Low -> broad plateau -> robust. High -> sharp peak -> fragile."""
    valid = [p for p in points if p.error is None and not math.isnan(p.sharpe_ratio)]
    if len(valid) < 2:
        return float("nan")
    sharpes = [p.sharpe_ratio for p in valid]
    baseline = next((p.sharpe_ratio for p in valid if p.value == stated_value), sharpes[0])
    spread = max(sharpes) - min(sharpes)
    denom = abs(baseline) if abs(baseline) > 1e-6 else 1e-6
    return spread / denom


def _robustness_label(peakiness: float) -> str:
    if math.isnan(peakiness):
        return "insufficient_data"
    if peakiness <= _ROBUST_PEAKINESS_MAX:
        return "robust (broad plateau)"
    if peakiness >= _FRAGILE_PEAKINESS_MIN:
        return "fragile (sharp peak)"
    return "moderate"
