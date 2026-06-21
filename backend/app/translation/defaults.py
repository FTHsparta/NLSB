"""Deterministic defaulting: sparse IR -> (full IR, assumptions).

The translator's system prompt instructs the LLM to populate only fields the
user explicitly stated and to omit any optional field it is not sure about
(a "sparse IR"). This module is the *only* place that invents values for
unstated fields — it runs in our code, not the model's, so the model cannot
hide or misreport what it assumed.

Every field this module fills in is recorded as an ``Assumption``. Fields
with no sensible default (``asset.ticker``, the ``entry`` condition itself)
are never defaulted: if they're missing, ``apply_defaults`` raises
``DefaultingError`` so the caller can re-prompt or surface a clear error
instead of silently guessing the one thing that defines the strategy.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

DEFAULT_RSI_PERIOD = 14
DEFAULT_SMA_PERIOD = 20
DEFAULT_EMA_PERIOD = 20
DEFAULT_INDICATOR_SOURCE = "close"
DEFAULT_ASSET_CLASS = "equity"
DEFAULT_POSITION_DIRECTION = "long"
DEFAULT_POSITION_SIZE = "full"

_DEFAULT_PERIOD_BY_TYPE = {
    "RSI": DEFAULT_RSI_PERIOD,
    "SMA": DEFAULT_SMA_PERIOD,
    "EMA": DEFAULT_EMA_PERIOD,
}

# A condition that is structurally valid but never true: "close < close".
# Used as the documented default when the user didn't state an exit —
# the position is simply never explicitly closed by a signal.
NO_EXIT_CONDITION = {"left": "close", "op": "<", "right": "close"}


class DefaultingError(ValueError):
    """Raised when a required (non-defaultable) field is missing from the sparse IR."""


@dataclass(frozen=True)
class Assumption:
    """One field the defaulting layer filled in because the user didn't state it."""

    field: str
    value: object
    reason: str


def apply_defaults(sparse_ir: dict) -> tuple[dict, list[Assumption]]:
    """Fill in unstated optional fields of *sparse_ir* with documented defaults.

    Returns ``(full_ir, assumptions)``. ``full_ir`` is not guaranteed to pass
    schema validation if the sparse IR is malformed in ways this function
    doesn't fix (e.g. an indicator referencing an unknown ``type``) — the
    caller is expected to schema-validate the result.

    Raises
    ------
    DefaultingError
        If a field with no sensible default is missing: ``asset.ticker`` or
        ``entry``.
    """
    ir = copy.deepcopy(sparse_ir)
    assumptions: list[Assumption] = []

    _default_asset(ir, assumptions)
    _default_indicators(ir, assumptions)
    _require_entry(ir)
    _default_exit(ir, assumptions)
    _default_position(ir, assumptions)
    _default_risk(ir, assumptions)

    return ir, assumptions


def _default_asset(ir: dict, assumptions: list[Assumption]) -> None:
    asset = ir.get("asset")
    if not isinstance(asset, dict) or not asset.get("ticker"):
        raise DefaultingError(
            "asset.ticker is required and has no default — the strategy "
            "must name a ticker."
        )
    if not asset.get("asset_class"):
        asset["asset_class"] = DEFAULT_ASSET_CLASS
        assumptions.append(
            Assumption(
                field="asset.asset_class",
                value=DEFAULT_ASSET_CLASS,
                reason="asset class not stated; defaulted to equity",
            )
        )
    ir["asset"] = asset


def _default_indicators(ir: dict, assumptions: list[Assumption]) -> None:
    indicators = ir.get("indicators") or []
    for ind in indicators:
        ind_id = ind.get("id", "<unnamed>")
        ind_type = ind.get("type")
        if not ind_type:
            raise DefaultingError(
                f"indicator {ind_id!r} is missing 'type' — has no default "
                "(the kind of indicator must be stated or inferable)."
            )

        if not ind.get("source"):
            ind["source"] = DEFAULT_INDICATOR_SOURCE
            assumptions.append(
                Assumption(
                    field=f"indicators.{ind_id}.source",
                    value=DEFAULT_INDICATOR_SOURCE,
                    reason=f"source price field for {ind_id} not stated; defaulted to close",
                )
            )

        params = ind.get("params") or {}
        if not params.get("period"):
            default_period = _DEFAULT_PERIOD_BY_TYPE.get(ind_type)
            if default_period is None:
                raise DefaultingError(
                    f"indicator {ind_id!r} has unknown type {ind_type!r} and "
                    "no period — cannot pick a default."
                )
            params["period"] = default_period
            assumptions.append(
                Assumption(
                    field=f"indicators.{ind_id}.params.period",
                    value=default_period,
                    reason=f"period for {ind_type} indicator {ind_id} not stated; "
                    f"defaulted to {default_period}",
                )
            )
        ind["params"] = params
    ir["indicators"] = indicators


def _require_entry(ir: dict) -> None:
    if not ir.get("entry"):
        raise DefaultingError(
            "entry condition is required and has no default — a strategy "
            "must say what triggers a buy."
        )


def _default_exit(ir: dict, assumptions: list[Assumption]) -> None:
    if not ir.get("exit"):
        ir["exit"] = copy.deepcopy(NO_EXIT_CONDITION)
        assumptions.append(
            Assumption(
                field="exit",
                value=NO_EXIT_CONDITION,
                reason="no exit condition stated; position is never explicitly "
                "closed by a signal (held until the end of the test window)",
            )
        )


def _default_position(ir: dict, assumptions: list[Assumption]) -> None:
    position = ir.get("position") or {}
    if not position.get("direction"):
        position["direction"] = DEFAULT_POSITION_DIRECTION
        assumptions.append(
            Assumption(
                field="position.direction",
                value=DEFAULT_POSITION_DIRECTION,
                reason="position direction not stated; defaulted to long (v1 is long-only)",
            )
        )
    if not position.get("size"):
        position["size"] = DEFAULT_POSITION_SIZE
        assumptions.append(
            Assumption(
                field="position.size",
                value=DEFAULT_POSITION_SIZE,
                reason="position sizing not stated; defaulted to full capital per trade",
            )
        )
    ir["position"] = position


def _default_risk(ir: dict, assumptions: list[Assumption]) -> None:
    risk = ir.get("risk")
    if risk is None:
        ir["risk"] = None
        assumptions.append(
            Assumption(
                field="risk",
                value=None,
                reason="no stop-loss/take-profit stated; defaulted to none",
            )
        )
        return

    if "stop_loss_pct" not in risk:
        risk["stop_loss_pct"] = None
        assumptions.append(
            Assumption(
                field="risk.stop_loss_pct",
                value=None,
                reason="no stop-loss stated; defaulted to none",
            )
        )
    if "take_profit_pct" not in risk:
        risk["take_profit_pct"] = None
        assumptions.append(
            Assumption(
                field="risk.take_profit_pct",
                value=None,
                reason="no take-profit stated; defaulted to none",
            )
        )
    ir["risk"] = risk
