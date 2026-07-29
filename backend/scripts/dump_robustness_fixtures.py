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

from app.robustness.robustness import run_robustness as _run_robustness
from app.translation.defaults import apply_defaults


def run_robustness(ir, price_data, assumptions, **kwargs):
    """`run_robustness` with the requested window filled in from the data.

    Phase 12B: every result carries a `window` block reporting what was asked
    for alongside what was judged. The HTTP path always supplies the requested
    dates; a builder calling the orchestrator directly would leave them null,
    which would make these fixtures unrepresentative of the payload the
    frontend actually receives. Defaulting them to the synthetic series' own
    bounds models the healthy case -- asked for exactly what existed -- while
    keeping the fields non-null so the renderer's tests exercise real values.
    """
    kwargs.setdefault("requested_start", price_data.index.min())
    kwargs.setdefault("requested_end", price_data.index.max())
    return _run_robustness(ir, price_data, assumptions, **kwargs)

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


def _two_segment_series(n_bull: int, n_bear: int, seed: int, bear_noise: float) -> pd.Series:
    """A clean uptrend followed by a noisier downtrend -- mirrors
    `tests/test_regime.py::_two_segment_series`, with `bear_noise`
    exposed because the bull-concentration fixtures below need real
    up-day noise IN the bear segment: that's what gives a same-window
    buy-and-hold benchmark a non-trivial share of its own gains from bear
    bars, which is the only way a strategy can be MORE bull-concentrated
    than its benchmark (see `app.robustness.regime`'s module docstring)."""
    rng = np.random.default_rng(seed)
    bull = 100 + np.linspace(0, 100, n_bull) + rng.normal(0, 0.3, n_bull)
    bear = bull[-1] + np.linspace(0, -100, n_bear) + rng.normal(0, bear_noise, n_bear)
    close = np.concatenate([bull, bear])
    idx = pd.date_range("2010-01-01", periods=len(close), freq="D")
    return pd.Series(close, index=idx, dtype=float)


def _sma_trend_following_ir(period: int = 200) -> dict:
    """Trend-following, not mean-reversion: long only while price is
    above its own SMA, flat otherwise. Deliberately uses the SAME period
    as `app.robustness.regime.MA_PERIOD` so the strategy is in the market
    almost exactly when the regime module's own bull/bear label says
    'bull' -- i.e. a strategy that, by construction, earns ~0 gains
    during bear-labeled bars, unlike the buy-and-hold benchmark it's
    compared against, which stays exposed (and keeps collecting bear-bar
    up-day gains) throughout."""
    return {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [{"id": "sma", "type": "SMA", "params": {"period": period}, "source": "close"}],
        "entry": {"left": "close", "op": "crosses_above", "right": "sma"},
        "exit": {"left": "close", "op": "crosses_below", "right": "sma"},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }


def build_bull_concentration_confirmed() -> dict:
    """Found by direct search over (seed, bear_noise) for
    `_two_segment_series` + `_sma_trend_following_ir`, the same
    construction `tests/test_regime.py`'s 4d integration test uses
    conceptually (trend-following strategy vs. its own buy-and-hold
    benchmark on a series with bear-segment up-day noise) -- but run
    through the REAL, unmocked orchestrator rather than a monkeypatched
    `run_ir_backtest_returns`, so this fixture is the genuine
    `run_robustness` output the frontend will actually receive, not a
    hand-shaped approximation of it. Lands at excess=0.3012, comfortably
    past `MARGINAL_BULL_EXCESS_CONFIRMED_THRESHOLD` (0.20)."""
    close = _two_segment_series(400, 400, seed=4, bear_noise=1.85)
    full_ir, assumptions = apply_defaults(_sma_trend_following_ir(200))
    return run_robustness(
        full_ir,
        _price_data(close),
        assumptions,
        in_sample_bars=200,
        out_of_sample_bars=80,
        step_bars=80,
        min_trades_for_confidence=3,
    )


def build_bull_concentration_provisional() -> dict:
    """Same construction as `build_bull_concentration_confirmed`, a
    different (seed, bear_noise) pair found to land excess=0.1635 --
    inside the 0.15-0.20 'provisional' band rather than past it. The
    search space is genuinely cliff-like (a trend-following strategy's
    entries/exits are discrete crossing events, not a smooth dial), so
    this exact pair is load-bearing: re-running the search with a wider
    net would likely find a different pair, but this one is pinned by
    `test_robustness_fixtures.py` and should not be casually swapped."""
    close = _two_segment_series(400, 400, seed=174, bear_noise=1.84)
    full_ir, assumptions = apply_defaults(_sma_trend_following_ir(200))
    return run_robustness(
        full_ir,
        _price_data(close),
        assumptions,
        in_sample_bars=200,
        out_of_sample_bars=80,
        step_bars=80,
        min_trades_for_confidence=3,
    )


def _multi_cycle_series(n_cycles: int, up: int, down: int, seed: int, noise: float, up_amp: float = 60.0, down_amp: float = -55.0) -> pd.Series:
    """Repeated up/down ramps with a net upward bias (``up_amp + down_amp > 0``)
    plus per-cycle noise. Unlike the single bull-then-bear `_two_segment_series`
    (which crosses a trend MA only once or twice, so a trend-follower makes
    ~0 OOS trades and the whole run lands UNTESTABLE), a MULTI-cycle series
    makes the trend-follower cross its SMA every cycle -- enough real
    round-trip trades per fold that walk-forward is genuinely testable, while
    sitting out each down-ramp keeps the strategy more bull-concentrated than
    its fully-invested benchmark."""
    rng = np.random.default_rng(seed)
    segments = [np.array([100.0])]
    for _ in range(n_cycles):
        base = segments[-1][-1]
        up_seg = base + np.linspace(0, up_amp, up) + rng.normal(0, noise, up)
        segments.append(up_seg)
        down_seg = up_seg[-1] + np.linspace(0, down_amp, down) + rng.normal(0, noise, down)
        segments.append(down_seg)
    close = np.concatenate(segments)
    idx = pd.date_range("2010-01-01", periods=len(close), freq="D")
    return pd.Series(close, index=idx, dtype=float)


def build_bull_concentration_with_verdict() -> dict:
    """The Phase 9 fixture: a NON-UNTESTABLE verdict AND a populated,
    confirmed bull-concentration flag co-occurring in one real result -- the
    combination none of the other fixtures cover (the two `bull_concentration_*`
    fixtures both land UNTESTABLE, because their single-segment series gives
    the trend-follower ~0 OOS trades). Found by a (period, cycles, seed,
    noise) search over `_multi_cycle_series` + `_sma_trend_following_ir`;
    this exact tuple lands verdict=SHAKY with excess=0.2023 (past the 0.20
    confirmed threshold) and OOS trades in every fold, run through the REAL,
    unmocked orchestrator. Deterministic (seeded RNG, no network). Pinned in
    `test_robustness_fixtures.py`; the tuple is load-bearing (the search space
    is cliff-like) and should not be casually swapped."""
    close = _multi_cycle_series(n_cycles=4, up=120, down=90, seed=4, noise=5.0)
    full_ir, assumptions = apply_defaults(_sma_trend_following_ir(50))
    return run_robustness(
        full_ir,
        _price_data(close),
        assumptions,
        in_sample_bars=300,
        out_of_sample_bars=150,
        step_bars=150,
        min_trades_for_confidence=3,
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
    _dump("bull_concentration_confirmed", build_bull_concentration_confirmed())
    _dump("bull_concentration_provisional", build_bull_concentration_provisional())
    _dump("bull_concentration_with_verdict", build_bull_concentration_with_verdict())
    _dump("no_exit", build_no_exit())


if __name__ == "__main__":
    main()
