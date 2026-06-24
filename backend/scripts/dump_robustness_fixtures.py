"""Dump one real `run_robustness` output per verdict state (+ one no-exit
result) as JSON fixtures for the frontend renderer's tests to build against.

Why a script that RUNS the orchestrator, instead of hand-authoring the JSON:
hand-authored fixtures drift from `RESULT_KEYS`/the real dataclass shapes the
moment a backend field is renamed, added, or removed, and nothing catches it
until the frontend silently fails to render the new shape in production. By
construction, the fixtures here are byte-for-byte whatever `run_robustness`
actually returns on these canned (synthetic, seeded, no network) inputs --
so re-running this script after any backend change is also a manual check
that the frontend's assumptions about the schema still hold.

Each price series/IR/window combination below was found by direct
experimentation specifically to land in the target verdict bucket on this
codebase's actual thresholds (see `app.robustness.verdict`) -- they are not
meant to be realistic trading strategies, just deterministic (seeded RNG, no
network) inputs that exercise each state for real.

Run from `backend/`: `python -m scripts.dump_robustness_fixtures`
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from app.robustness.robustness import run_robustness
from app.translation.defaults import apply_defaults

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "fixtures" / "robustness"


def _price_data(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close})


def _oscillating_close(n: int) -> pd.Series:
    """Sharp up/down blocks (not a smooth sine) -- matches the fixture used
    in `test_translation_no_exit_backtest.py`, which confirmed RSI(14)<30
    actually fires on this shape. A smooth, small-amplitude sine wave (tried
    first) never moved RSI(14) below 30 at all -- the no-exit branch needs
    an entry to actually fire to be a meaningful fixture."""
    block = np.concatenate([-np.ones(20), np.ones(20)])
    reps = int(np.ceil((n - 1) / len(block)))
    deltas = np.tile(block, reps)[: n - 1]
    close = 100 + np.concatenate([[0], np.cumsum(deltas)])
    idx = pd.date_range("2010-01-01", periods=n, freq="D")
    return pd.Series(close, index=idx, dtype=float)


def _ou_process(n: int, seed: int, theta: float = 0.15, mu: float = 100.0, sigma: float = 0.6, drift: float = 0.03) -> pd.Series:
    """Mean-reverting (Ornstein-Uhlenbeck) synthetic series with a small
    upward drift -- gives a long-only mean-reversion strategy many genuine
    round-trip trades with a consistent edge across both IS and OOS."""
    rng = np.random.default_rng(seed)
    x = np.empty(n)
    x[0] = mu
    for t in range(1, n):
        x[t] = x[t - 1] + theta * (mu - x[t - 1]) + sigma * rng.standard_normal() + drift
    idx = pd.date_range("2010-01-01", periods=n, freq="D")
    return pd.Series(x, index=idx, dtype=float)


def _osc_then_crash(n_osc: int, n_crash: int, period: int = 14, amp: float = 4.0, crash: float = -60.0) -> pd.Series:
    """A clean oscillation (IS) followed by a hard, non-oscillating
    downtrend (OOS) -- a long-only mean-reversion strategy tuned on the
    oscillating segment ("buy the dip") keeps buying dips straight into the
    crash, the textbook walk-forward overfitting signature."""
    t1 = np.arange(n_osc)
    seg1 = 100 + amp * np.sin(2 * np.pi * t1 / period)
    seg2 = seg1[-1] + np.linspace(0, crash, n_crash)
    close = np.concatenate([seg1, seg2])
    idx = pd.date_range("2010-01-01", periods=len(close), freq="D")
    return pd.Series(close, index=idx, dtype=float)


def _sma_crossover_ir(period: int = 20) -> dict:
    """Mean-reversion: buy when price crosses below its SMA, sell when it
    crosses back above. Both operands of entry/exit are indicator/price
    series (no numeric threshold operand), so sensitivity only sweeps the
    SMA period -- one tunable, not the period-and-two-thresholds combination
    an RSI strategy gives, which kept tripping a spurious "fragile" label
    from threshold sensitivity alone while exploring fixtures for PASS."""
    return {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [{"id": "sma20", "type": "SMA", "params": {"period": period}, "source": "close"}],
        "entry": {"left": "close", "op": "crosses_below", "right": "sma20"},
        "exit": {"left": "close", "op": "crosses_above", "right": "sma20"},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }


def _rsi_ir(period: int = 14, lo: float = 25, hi: float = 75) -> dict:
    return {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [{"id": "rsi", "type": "RSI", "params": {"period": period}, "source": "close"}],
        "entry": {"left": "rsi", "op": "<", "right": lo},
        "exit": {"left": "rsi", "op": ">", "right": hi},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }


def _null_out_non_finite_floats(obj, path: str = "$"):
    """Real backtest output legitimately contains NaN (e.g. a regime cell
    with zero-variance returns has no defined Sharpe) -- that's information
    the renderer needs to show as "not available," not an error to raise
    on. But `json.dump`'s default `allow_nan=True` would silently emit the
    non-standard `NaN`/`Infinity` tokens Python accepts and the JSON spec
    (and `JSON.parse` in JS) doesn't, which would make the fixture
    unparseable by the very frontend it's meant to feed. So: convert
    NaN/Infinity to `null` here, explicitly, rather than let `json.dump`
    emit something downstream can't read -- the same "not available" value
    a renderer would show for any other missing field."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {key: _null_out_non_finite_floats(value, f"{path}.{key}") for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_null_out_non_finite_floats(value, f"{path}[{i}]") for i, value in enumerate(obj)]
    return obj


def _dump(name: str, result: dict) -> None:
    sanitized = _null_out_non_finite_floats(result)
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURES_DIR / f"{name}.json"
    path.write_text(json.dumps(sanitized, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    verdict = result["verdict"]["verdict"] if result["kind"] == "full" else "NO_EXIT"
    print(f"wrote {path.relative_to(FIXTURES_DIR.parents[2])} -- kind={result['kind']} verdict={verdict}")


def build_pass() -> dict:
    close = _ou_process(700, seed=2)
    full_ir, assumptions = apply_defaults(_sma_crossover_ir(20))
    return run_robustness(
        full_ir,
        _price_data(close),
        assumptions,
        in_sample_bars=200,
        out_of_sample_bars=80,
        step_bars=80,
        min_trades_for_confidence=3,
    )


def build_shaky() -> dict:
    close = _ou_process(700, seed=5)
    full_ir, assumptions = apply_defaults(_sma_crossover_ir(20))
    return run_robustness(
        full_ir,
        _price_data(close),
        assumptions,
        in_sample_bars=200,
        out_of_sample_bars=80,
        step_bars=80,
        min_trades_for_confidence=3,
    )


def build_likely_overfit() -> dict:
    close = _osc_then_crash(300, 150, period=14, amp=4.0, crash=-60.0)
    full_ir, assumptions = apply_defaults(_rsi_ir(14, 30, 70))
    return run_robustness(
        full_ir,
        _price_data(close),
        assumptions,
        in_sample_bars=250,
        out_of_sample_bars=100,
        step_bars=100,
        min_trades_for_confidence=5,
    )


def build_untestable() -> dict:
    """Both the WF axis AND the DSR axis are untestable here (sparse
    trades, wild per-fold Sharpes) -- exercises the Phase 4c calibration fix
    where a DSR-fail must not escape the untestable guard."""
    close = _osc_then_crash(250, 120, period=20, amp=3.0, crash=-15.0)
    full_ir, assumptions = apply_defaults(_rsi_ir(14, 25, 75))
    return run_robustness(
        full_ir,
        _price_data(close),
        assumptions,
        in_sample_bars=200,
        out_of_sample_bars=80,
        step_bars=80,
        # default min_trades_for_confidence (10) -- deliberately not loosened,
        # so both folds land low_confidence on these short windows.
    )


def build_no_exit() -> dict:
    sparse_ir = {
        "asset": {"ticker": "SPY"},
        "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        # no "exit" key -> defaults to the no-exit sentinel
    }
    full_ir, assumptions = apply_defaults(sparse_ir)
    close = _oscillating_close(200)
    return run_robustness(full_ir, _price_data(close), assumptions)


def main() -> None:
    _dump("pass", build_pass())
    _dump("shaky", build_shaky())
    _dump("likely_overfit", build_likely_overfit())
    _dump("untestable", build_untestable())
    _dump("no_exit", build_no_exit())


if __name__ == "__main__":
    main()
