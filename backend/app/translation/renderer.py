"""Deterministic plain-English restatement of a full strategy IR.

This is a PURE function: no network call, no LLM, no randomness. It consumes
the exact same IR object the safe interpreter (`app.translation.interpreter`)
will run, so "what you confirm is what runs" is structural, not a promise —
there is no second model call that could drift from the IR.
"""

from __future__ import annotations

from app.translation.defaults import NO_EXIT_CONDITION, SEVERITY_WARNING, Assumption

_OP_ENGLISH = {
    "<": "is below",
    ">": "is above",
    "<=": "is at or below",
    ">=": "is at or above",
    "crosses_above": "crosses above",
    "crosses_below": "crosses below",
}

# The always-false sentinel ("close < close") is a structurally-valid
# condition, but rendering it literally ("sell when close price is below
# close price") would hide the fact that the position is never closed.
# Always special-case it to prose that says what actually happens.
_NO_EXIT_PROSE = (
    "No exit rule given — I held the position from your first entry signal "
    "to the end of the data. These results approximate buy-and-hold from "
    "that date, not a round-trip strategy."
)


def render_confirmation(full_ir: dict, assumptions: list[Assumption]) -> str:
    """Render the two-section confirmation text for a fully-defaulted IR.

    Section 1 is the plain-English strategy itself (entry/exit/position/risk).
    Section 2 splits "You specified" from "I assumed (you didn't specify
    these)", driven entirely by *assumptions* — the list `apply_defaults`
    produced, not a second guess by this function.
    """
    indicators_by_id = {ind["id"]: ind for ind in full_ir.get("indicators", [])}
    assumed_fields = {a.field for a in assumptions}

    asset = full_ir["asset"]
    position = full_ir["position"]
    risk = full_ir.get("risk")

    lines: list[str] = []
    lines.append(
        f"Here's what I'm about to backtest on {asset['ticker']} ({asset['asset_class']}):"
    )
    lines.append(f"- Entry: buy when {_condition_to_english(full_ir['entry'], indicators_by_id)}")
    if full_ir["exit"] == NO_EXIT_CONDITION:
        lines.append(f"- Exit: {_NO_EXIT_PROSE}")
    else:
        lines.append(f"- Exit: sell when {_condition_to_english(full_ir['exit'], indicators_by_id)}")
    lines.append(
        f"- Position: {position['direction']} only, {position['size']} capital allocation per trade"
    )
    if risk:
        sl = risk.get("stop_loss_pct")
        tp = risk.get("take_profit_pct")
        if sl is not None:
            lines.append(f"- Stop-loss: {sl * 100:.1f}% below entry price")
        if tp is not None:
            lines.append(f"- Take-profit: {tp * 100:.1f}% above entry price")

    lines.append("")
    lines.append("You specified:")
    stated = _stated_summary(full_ir, indicators_by_id, assumed_fields)
    if stated:
        lines.extend(f"- {item}" for item in stated)
    else:
        lines.append("- (nothing beyond the basic strategy structure)")

    warnings = [a for a in assumptions if a.severity == SEVERITY_WARNING]
    notes = [a for a in assumptions if a.severity != SEVERITY_WARNING]

    if warnings:
        lines.append("")
        lines.append("⚠ Heads up — these assumptions change what the result means:")
        for a in warnings:
            lines.append(f"- {a.reason}")

    lines.append("")
    lines.append("I assumed (you didn't specify these):")
    if notes:
        for a in notes:
            lines.append(f"- {a.field}: {_fmt_value(a.value)} — {a.reason}")
    elif warnings:
        lines.append("- (nothing routine — see the heads-up above)")
    else:
        lines.append("- (nothing — you specified every field)")

    return "\n".join(lines)


def _stated_summary(
    full_ir: dict, indicators_by_id: dict, assumed_fields: set[str]
) -> list[str]:
    stated: list[str] = []
    asset = full_ir["asset"]
    stated.append(f"ticker: {asset['ticker']}")
    if "asset.asset_class" not in assumed_fields:
        stated.append(f"asset class: {asset['asset_class']}")

    stated.append("entry condition")
    if "exit" not in assumed_fields:
        stated.append("exit condition")

    for ind_id, ind in indicators_by_id.items():
        prefix = f"indicators.{ind_id}."
        if not any(f.startswith(prefix) for f in assumed_fields):
            stated.append(
                f"{ind_id}: {ind['type']}({ind['params']['period']}) on {ind['source']}"
            )

    if "position.direction" not in assumed_fields and "position.size" not in assumed_fields:
        stated.append("position sizing")

    risk = full_ir.get("risk")
    if risk is not None and "risk" not in assumed_fields:
        if "risk.stop_loss_pct" not in assumed_fields and risk.get("stop_loss_pct") is not None:
            stated.append("stop-loss")
        if "risk.take_profit_pct" not in assumed_fields and risk.get("take_profit_pct") is not None:
            stated.append("take-profit")

    return stated


def _condition_to_english(cond: dict, indicators_by_id: dict) -> str:
    if "all_of" in cond:
        parts = [_condition_to_english(c, indicators_by_id) for c in cond["all_of"]]
        return " AND ".join(f"({p})" for p in parts)
    if "any_of" in cond:
        parts = [_condition_to_english(c, indicators_by_id) for c in cond["any_of"]]
        return " OR ".join(f"({p})" for p in parts)

    left = _operand_to_english(cond["left"], indicators_by_id)
    right = _operand_to_english(cond["right"], indicators_by_id)
    op_en = _OP_ENGLISH[cond["op"]]
    return f"{left} {op_en} {right}"


def _operand_to_english(operand, indicators_by_id: dict) -> str:
    if isinstance(operand, (int, float)):
        return _fmt_value(operand)
    if operand in indicators_by_id:
        ind = indicators_by_id[operand]
        return f"{ind['type']}({ind['params']['period']})"
    return f"{operand} price"


def _fmt_value(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
