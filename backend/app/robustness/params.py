"""Extract tunable parameters from a strategy IR, with a neighborhood grid
around each stated value.

Shared by `sensitivity.py` (one-at-a-time sweeps) and (in Phase 4b)
`walk_forward.py` (in-sample optimization over the same grid). Operates on
a full, schema-valid IR (after `app.translation.defaults.apply_defaults`) —
it does not call the LLM and does not care whether a value was stated or
defaulted, only what the final value is.

Two kinds of tunable parameter are extracted:
  - "period": an indicator's `params.period` (e.g. RSI period, MA length).
  - "threshold": a numeric constant operand in the entry/exit condition tree
    (e.g. the 30 in "RSI < 30").

Grid rule (ours, documented here since there's no external standard):
  - period: 5-point grid, stated value +/- {0, 2, 4} bars, clipped to >= 1.
    period=14 -> [10, 12, 14, 16, 18].
  - threshold: 5-point grid, stated value +/- {0, step, 2*step} where
    step = max(1, round(abs(value) * 0.1)) (10% of the stated value, at
    least 1). threshold=30 -> step=3 -> [24, 27, 30, 33, 36].
Both grids always include the stated value itself (so sensitivity can use
it as the baseline) and are deduplicated/sorted.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

PERIOD_OFFSETS = (-4, -2, 0, 2, 4)
THRESHOLD_OFFSET_MULTIPLES = (-2, -1, 0, 1, 2)


@dataclass(frozen=True)
class TunableParam:
    """One numeric value in the IR that sensitivity/walk-forward can sweep.

    ``path`` is a tuple of dict keys / list indices locating the value
    inside the IR (e.g. ``("indicators", 0, "params", "period")`` or
    ``("entry", "all_of", 0, "right")``) — usable with `get_in`/`set_in`.
    """

    param_id: str
    path: tuple
    value: float
    kind: str  # "period" | "threshold"
    grid: tuple


def extract_tunable_params(ir: dict) -> list[TunableParam]:
    """Walk *ir* and return every tunable parameter with its neighborhood grid."""
    params: list[TunableParam] = []

    for i, ind in enumerate(ir.get("indicators", [])):
        period = ind["params"]["period"]
        path = ("indicators", i, "params", "period")
        params.append(
            TunableParam(
                param_id=f"indicators.{ind['id']}.period",
                path=path,
                value=period,
                kind="period",
                grid=_period_grid(period),
            )
        )

    for section in ("entry", "exit"):
        for path_suffix, value in _walk_condition(ir[section], ()):
            path = (section, *path_suffix)
            params.append(
                TunableParam(
                    param_id=f"{section}.{'.'.join(str(p) for p in path_suffix)}",
                    path=path,
                    value=value,
                    kind="threshold",
                    grid=_threshold_grid(value),
                )
            )

    return params


def _walk_condition(cond: dict, prefix: tuple):
    if "all_of" in cond:
        for i, c in enumerate(cond["all_of"]):
            yield from _walk_condition(c, prefix + ("all_of", i))
    elif "any_of" in cond:
        for i, c in enumerate(cond["any_of"]):
            yield from _walk_condition(c, prefix + ("any_of", i))
    else:
        for side in ("left", "right"):
            val = cond[side]
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                yield prefix + (side,), val


def _period_grid(period: int) -> tuple:
    values = {max(1, period + offset) for offset in PERIOD_OFFSETS}
    return tuple(sorted(values))


def _threshold_grid(value: float) -> tuple:
    step = max(1, round(abs(value) * 0.1))
    values = {value + multiple * step for multiple in THRESHOLD_OFFSET_MULTIPLES}
    return tuple(sorted(values))


def get_in(ir: dict, path: tuple):
    """Read the value at *path* inside *ir* (dict keys / list indices)."""
    node = ir
    for key in path:
        node = node[key]
    return node


def set_in_copy(ir: dict, path: tuple, value) -> dict:
    """Return a deep copy of *ir* with the value at *path* replaced."""
    new_ir = copy.deepcopy(ir)
    node = new_ir
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return new_ir
