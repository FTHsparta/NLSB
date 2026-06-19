"""Safe strategy IR interpreter.

Security boundary: NO exec/eval is used anywhere in this module. The
interpreter only handles a hard-coded whitelist of indicator types (RSI,
SMA, EMA) and comparison operators (<, >, <=, >=, crosses_above,
crosses_below). Any IR that references a type or operator outside the
whitelist is rejected with IRInterpreterError before any computation runs.

This module is the sole code path from IR → vectorbt-ready signals.
"""

import json
from pathlib import Path
from typing import Union

import jsonschema
import pandas as pd

from app.engine.indicators import ema, sma, wilder_rsi
from app.engine.signals import shift_for_next_bar_execution

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_PATH = Path(__file__).parent / "strategy_ir.schema.json"
_SCHEMA: dict = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))

# ---------------------------------------------------------------------------
# Security whitelists (defence in depth — the schema already enumerates
# these, but the interpreter enforces them independently so a malformed IR
# that somehow bypasses schema validation cannot trigger arbitrary code).
# ---------------------------------------------------------------------------

_ALLOWED_INDICATOR_TYPES: frozenset[str] = frozenset({"RSI", "SMA", "EMA"})
_ALLOWED_OPERATORS: frozenset[str] = frozenset({"<", ">", "<=", ">=", "crosses_above", "crosses_below"})
_PRICE_FIELDS: frozenset[str] = frozenset({"close", "open", "high", "low"})

# Mapping from lowercase IR price-field name → DataFrame column name (yfinance convention).
_PRICE_COL: dict[str, str] = {
    "close": "Close",
    "open": "Open",
    "high": "High",
    "low": "Low",
}


# ---------------------------------------------------------------------------
# Public errors
# ---------------------------------------------------------------------------


class IRInterpreterError(ValueError):
    """Raised when the IR is structurally invalid or references unsupported operations."""


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def validate_ir(ir: dict) -> None:
    """Validate *ir* against the JSON schema.

    Raises ``jsonschema.ValidationError`` on failure.  Callers that want a
    single error type can catch ``(IRInterpreterError, jsonschema.ValidationError)``.
    """
    jsonschema.validate(ir, _SCHEMA)


# ---------------------------------------------------------------------------
# Warmup computation
# ---------------------------------------------------------------------------


def compute_ir_warmup(ir: dict) -> int:
    """Return the number of leading bars to discard before the first valid signal.

    Each indicator consumes a number of bars before it produces a non-NaN
    value; the no-lookahead shift adds one more bar on top.  The effective
    window starts after ``warmup`` bars, matching the convention in
    ``run_rsi_backtest``.
    """
    if not ir.get("indicators"):
        return 1  # just the shift
    return max(_indicator_lookback(ind) for ind in ir["indicators"])


def _indicator_lookback(ind: dict) -> int:
    """Bars consumed by indicator + shift before the first actionable signal."""
    t = ind["type"]
    period: int = ind["params"]["period"]
    if t == "RSI":
        # wilder_rsi produces NaN for bars 0..(period-1); first value at bar
        # `period`.  The no-lookahead shift makes it actionable at bar
        # `period+1`.  warmup = period + 1.
        return period + 1
    elif t in ("SMA", "EMA"):
        # rolling(period) produces NaN for bars 0..(period-2); first value at
        # bar `period-1`.  After shift: actionable at bar `period`.
        # EMA (ewm) actually starts at bar 0, but we use `period` as a
        # conservative warmup so strategies mixing SMA and EMA with the same
        # period are treated consistently.
        return period
    else:
        raise IRInterpreterError(
            f"Unknown indicator type {t!r}. "
            f"Allowed types: {sorted(_ALLOWED_INDICATOR_TYPES)}"
        )


# ---------------------------------------------------------------------------
# Core interpreter
# ---------------------------------------------------------------------------


def interpret_ir(
    ir: dict,
    price_data: pd.DataFrame,
    *,
    validate: bool = True,
) -> tuple[pd.Series, pd.Series]:
    """Turn a strategy IR into ``(entry_signals, exit_signals)``.

    Both returned series are shifted one bar forward (no-lookahead
    convention — a signal computed from bar ``t``'s close triggers execution
    at bar ``t+1``'s close).  They cover the full index of *price_data*;
    the caller should trim the first ``compute_ir_warmup(ir)`` bars before
    passing to vectorbt.

    Parameters
    ----------
    ir:
        Strategy IR dict.  Must be valid against the JSON schema.
    price_data:
        DataFrame with columns Open, High, Low, Close (yfinance convention).
    validate:
        If True (default), schema-validate *ir* first.  Pass False only in
        tests that deliberately supply a malformed IR to exercise the
        interpreter's own whitelist checks.

    Raises
    ------
    jsonschema.ValidationError
        If *validate=True* and *ir* fails schema validation.
    IRInterpreterError
        If any indicator type or operator is not in the whitelist, or if an
        operand string cannot be resolved to a known indicator id or price field.
    """
    if validate:
        validate_ir(ir)

    # ------------------------------------------------------------------
    # Build named indicator series (whitelisted types only)
    # ------------------------------------------------------------------
    indicator_series: dict[str, pd.Series] = {}
    for ind in ir.get("indicators", []):
        ind_type: str = ind["type"]
        if ind_type not in _ALLOWED_INDICATOR_TYPES:
            raise IRInterpreterError(
                f"Indicator type {ind_type!r} is not in the whitelist. "
                f"Allowed: {sorted(_ALLOWED_INDICATOR_TYPES)}"
            )
        period: int = ind["params"]["period"]
        source_col = _PRICE_COL[ind["source"]]
        src: pd.Series = price_data[source_col]

        if ind_type == "RSI":
            series = wilder_rsi(src, period=period)
        elif ind_type == "SMA":
            series = sma(src, period=period)
        elif ind_type == "EMA":
            series = ema(src, period=period)
        else:
            # Unreachable after the whitelist check above, but keeps mypy happy.
            raise IRInterpreterError(f"Unknown indicator type: {ind_type!r}")

        indicator_series[ind["id"]] = series

    # ------------------------------------------------------------------
    # Build price field lookup
    # ------------------------------------------------------------------
    price_series: dict[str, pd.Series] = {
        field: price_data[col]
        for field, col in _PRICE_COL.items()
        if col in price_data.columns
    }

    # ------------------------------------------------------------------
    # Operand resolver
    # ------------------------------------------------------------------

    def resolve_operand(operand: Union[int, float, str]) -> Union[float, pd.Series]:
        if isinstance(operand, (int, float)):
            return float(operand)
        if operand in indicator_series:
            return indicator_series[operand]
        if operand in price_series:
            return price_series[operand]
        raise IRInterpreterError(
            f"Operand {operand!r} is neither a known indicator id "
            f"({sorted(indicator_series)}) nor a price field "
            f"({sorted(price_series)})."
        )

    # ------------------------------------------------------------------
    # Condition tree evaluator (recursive, no eval/exec)
    # ------------------------------------------------------------------

    def eval_condition(cond: dict) -> pd.Series:
        if "all_of" in cond:
            parts = [eval_condition(c) for c in cond["all_of"]]
            result = parts[0]
            for p in parts[1:]:
                result = result & p
            return result
        if "any_of" in cond:
            parts = [eval_condition(c) for c in cond["any_of"]]
            result = parts[0]
            for p in parts[1:]:
                result = result | p
            return result
        return _eval_comparison(cond, resolve_operand, price_data.index)

    raw_entries = eval_condition(ir["entry"])
    raw_exits = eval_condition(ir["exit"])

    entries = shift_for_next_bar_execution(raw_entries)
    exits = shift_for_next_bar_execution(raw_exits)
    return entries, exits


# ---------------------------------------------------------------------------
# Comparison evaluation helpers (module-private)
# ---------------------------------------------------------------------------


def _eval_comparison(
    comp: dict,
    resolve_operand,
    index: pd.Index,
) -> pd.Series:
    op: str = comp["op"]
    if op not in _ALLOWED_OPERATORS:
        raise IRInterpreterError(
            f"Operator {op!r} is not in the whitelist. "
            f"Allowed: {sorted(_ALLOWED_OPERATORS)}"
        )

    left = resolve_operand(comp["left"])
    right = resolve_operand(comp["right"])

    left_s = _ensure_series(left, index)

    if op == "<":
        result = left_s < right
    elif op == ">":
        result = left_s > right
    elif op == "<=":
        result = left_s <= right
    elif op == ">=":
        result = left_s >= right
    elif op == "crosses_above":
        result = _crosses_above(left_s, right)
    elif op == "crosses_below":
        result = _crosses_below(left_s, right)
    else:
        raise IRInterpreterError(f"Unhandled operator: {op!r}")  # unreachable

    return result.fillna(False)


def _ensure_series(val: Union[float, pd.Series], index: pd.Index) -> pd.Series:
    if isinstance(val, pd.Series):
        return val
    return pd.Series(float(val), index=index)


def _crosses_above(
    left: pd.Series, right: Union[float, pd.Series]
) -> pd.Series:
    """True on bars where *left* transitions from <= *right* to > *right*."""
    if isinstance(right, pd.Series):
        return (left.shift(1) <= right.shift(1)) & (left > right)
    r = float(right)
    return (left.shift(1) <= r) & (left > r)


def _crosses_below(
    left: pd.Series, right: Union[float, pd.Series]
) -> pd.Series:
    """True on bars where *left* transitions from >= *right* to < *right*."""
    if isinstance(right, pd.Series):
        return (left.shift(1) >= right.shift(1)) & (left < right)
    r = float(right)
    return (left.shift(1) >= r) & (left < r)
