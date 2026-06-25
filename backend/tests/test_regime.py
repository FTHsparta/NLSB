import math

import numpy as np
import pandas as pd
import pytest

from app.robustness import regime as regime_module
from app.robustness.regime import run_regime_analysis


def _price_data(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close})


def _two_segment_series(n_bull: int = 400, n_bear: int = 400) -> pd.Series:
    """A clean, long uptrend followed by a clean, long downtrend -- long
    enough that the 200-day MA and 60-day vol windows have settled well
    before the segment boundary, so labels near the end of each segment are
    unambiguous."""
    rng = np.random.default_rng(1)
    bull = 100 + np.linspace(0, 100, n_bull) + rng.normal(0, 0.3, n_bull)
    bear = bull[-1] + np.linspace(0, -100, n_bear) + rng.normal(0, 0.3, n_bear)
    close = np.concatenate([bull, bear])
    idx = pd.date_range("2010-01-01", periods=len(close), freq="D")
    return pd.Series(close, index=idx, dtype=float)


def _simple_ir(period: int = 14):
    return {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [
            {"id": "rsi14", "type": "RSI", "params": {"period": period}, "source": "close"}
        ],
        "entry": {"left": "rsi14", "op": "<", "right": 50},
        "exit": {"left": "rsi14", "op": ">", "right": 50},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }


# ---------------------------------------------------------------------------
# Regime labeling rule (documented: price vs 200-day MA; 60-day vol vs median)
# ---------------------------------------------------------------------------


def test_trend_label_is_bull_well_into_a_long_uptrend():
    close = _two_segment_series(400, 400)
    labels = regime_module._regime_labels(close)
    # well past the 200-day MA warmup, deep in the uptrend
    assert labels.iloc[390].startswith("bull")


def test_trend_label_is_bear_well_into_a_long_downtrend():
    close = _two_segment_series(400, 400)
    labels = regime_module._regime_labels(close)
    # near the end of the downtrend segment
    assert labels.iloc[-10].startswith("bear")


def test_warmup_bars_before_first_ma200_value_are_unlabeled():
    close = _two_segment_series(400, 400)
    labels = regime_module._regime_labels(close)
    assert labels.iloc[0] is None
    assert labels.iloc[regime_module.MA_PERIOD - 2] is None


# ---------------------------------------------------------------------------
# Per-regime attribution (real run_ir_backtest_returns -- single source of truth)
# ---------------------------------------------------------------------------


def test_share_of_time_across_regimes_sums_to_one():
    close = _two_segment_series(400, 400)
    price_data = _price_data(close)
    report = run_regime_analysis(_simple_ir(), price_data)
    total_share = sum(b.share_of_time for b in report.breakdowns)
    assert total_share == pytest.approx(1.0, abs=1e-9)


def test_both_bull_and_bear_regimes_appear_in_breakdown():
    close = _two_segment_series(400, 400)
    price_data = _price_data(close)
    report = run_regime_analysis(_simple_ir(), price_data)
    regime_names = {b.regime for b in report.breakdowns}
    assert any(r.startswith("bull") for r in regime_names)
    assert any(r.startswith("bear") for r in regime_names)


def test_regime_attribution_uses_run_ir_backtest_returns_exactly_once(monkeypatch):
    """Every figure must come from the SAME underlying backtest call --
    regime.py must not run a second, independent simulation."""
    calls = []
    real = regime_module.run_ir_backtest_returns

    def _spy(ir, price_data, **kwargs):
        calls.append(1)
        return real(ir, price_data, **kwargs)

    monkeypatch.setattr(regime_module, "run_ir_backtest_returns", _spy)

    close = _two_segment_series(300, 300)
    price_data = _price_data(close)
    run_regime_analysis(_simple_ir(), price_data)
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Concentration flag (crafted, monkeypatched returns -- precise control)
# ---------------------------------------------------------------------------


def test_concentration_flag_triggers_when_one_regime_owns_almost_all_gains(monkeypatch):
    close = _two_segment_series(400, 400)
    # Find the exact bars belonging to a single combined regime (trend x
    # vol) and put ALL gains only there, so the test doesn't depend on
    # guessing where the vol-median split falls within the trend segment.
    labels = regime_module._regime_labels(close)
    target_regime = labels.dropna().value_counts().idxmax()
    target_mask = labels == target_regime

    def _fake_returns(ir, price_data, **kwargs):
        gains = pd.Series(0.0, index=price_data.index)
        gains[target_mask.reindex(price_data.index, fill_value=False)] = 0.01
        entries = pd.Series(False, index=price_data.index)
        return gains, entries

    monkeypatch.setattr(regime_module, "run_ir_backtest_returns", _fake_returns)

    price_data = _price_data(close)
    report = run_regime_analysis(_simple_ir(), price_data)

    assert report.concentrated_regime == target_regime
    assert report.concentration_share >= regime_module.CONCENTRATION_SHARE_THRESHOLD


def test_no_concentration_flag_when_gains_are_spread_across_regimes(monkeypatch):
    close = _two_segment_series(400, 400)

    def _fake_returns(ir, price_data, **kwargs):
        n = len(price_data)
        gains = pd.Series(0.0, index=price_data.index)
        gains.iloc[:] = 0.005  # uniform small gain everywhere
        entries = pd.Series(False, index=price_data.index)
        return gains, entries

    monkeypatch.setattr(regime_module, "run_ir_backtest_returns", _fake_returns)

    price_data = _price_data(close)
    report = run_regime_analysis(_simple_ir(), price_data)

    assert report.concentrated_regime is None
    assert report.concentration_share is None


# ---------------------------------------------------------------------------
# Marginal bull concentration -- benchmark-relative excess (Phase 4d).
# Unit-level tests against `_detect_bull_concentration` directly hit the
# four invariants precisely; integration-level tests below go through
# `run_regime_analysis` to confirm the wiring (benchmark derived from the
# SAME price series, not a parameter) actually behaves this way end to end.
# ---------------------------------------------------------------------------


def _bull_bear_valid(n_bull: int, n_bear: int) -> tuple:
    """A trend_labels/valid pair with no NaN warmup gaps -- the unit tests
    below construct daily_returns/benchmark_returns directly and don't need
    a real 200-day MA warmup, just a clean bull/bear split to mask against."""
    idx = pd.date_range("2010-01-01", periods=n_bull + n_bear, freq="D")
    trend_labels = pd.Series(["bull"] * n_bull + ["bear"] * n_bear, index=idx, dtype=object)
    valid = pd.Series(True, index=idx)
    return trend_labels, valid


def test_invariant_a_zero_excess_does_not_flag_regardless_of_absolute_share():
    """A strategy whose bull_share equals the benchmark's bull_share must
    not flag, even though the absolute share (90%) would have tripped the
    old unconditional 80% threshold."""
    trend_labels, valid = _bull_bear_valid(180, 20)
    idx = trend_labels.index
    # Both strategy and benchmark earn the same gains pattern -> identical
    # bull_share (90% of bars are bull, gains are uniform) -> excess = 0.
    returns = pd.Series(0.01, index=idx)
    flags = regime_module._detect_bull_concentration(returns, returns.copy(), valid, trend_labels)
    assert flags == ()


def test_invariant_b_excess_just_above_threshold_is_provisional():
    trend_labels, valid = _bull_bear_valid(100, 100)
    idx = trend_labels.index
    bull_mask = trend_labels == "bull"

    # Benchmark: gains split evenly 50/50 bull/bear -> benchmark_bull_share = 0.5.
    benchmark_returns = pd.Series(0.01, index=idx)

    # Strategy: bull_share = 0.68 -> excess = 0.18 (threshold 0.15 < 0.18 <= 0.20).
    strategy_returns = pd.Series(0.0, index=idx)
    n_bull_bars = int(bull_mask.sum())
    bull_positions = [i for i, v in enumerate(bull_mask) if v]
    bear_positions = [i for i, v in enumerate(bull_mask) if not v]
    # 68 of the 100 bull bars and 32 of the 100 bear bars carry equal-sized
    # gains -> bull share of total gains = 68 / (68 + 32) = 0.68.
    for i in bull_positions[:68]:
        strategy_returns.iloc[i] = 0.01
    for i in bear_positions[:32]:
        strategy_returns.iloc[i] = 0.01

    flags = regime_module._detect_bull_concentration(strategy_returns, benchmark_returns, valid, trend_labels)
    assert len(flags) == 1
    flag = flags[0]
    assert flag["flag"] == "bull_concentration"
    assert flag["excess"] == pytest.approx(0.18, abs=1e-4)
    assert flag["confidence"] == "provisional"
    assert n_bull_bars == 100  # sanity: the 50/50 split assumed above holds


def test_invariant_c_excess_well_above_band_is_confirmed():
    trend_labels, valid = _bull_bear_valid(100, 100)
    idx = trend_labels.index
    bull_mask = trend_labels == "bull"
    bull_positions = [i for i, v in enumerate(bull_mask) if v]
    bear_positions = [i for i, v in enumerate(bull_mask) if not v]

    benchmark_returns = pd.Series(0.0, index=idx)
    for i in bull_positions + bear_positions:
        benchmark_returns.iloc[i] = 0.01  # uniform -> benchmark_bull_share = 0.5

    # Strategy: bull share of gains = 0.72 -> excess = 0.22 (> 0.20 -> confirmed).
    strategy_returns = pd.Series(0.0, index=idx)
    for i in bull_positions[:72]:
        strategy_returns.iloc[i] = 0.01
    for i in bear_positions[:28]:
        strategy_returns.iloc[i] = 0.01

    flags = regime_module._detect_bull_concentration(strategy_returns, benchmark_returns, valid, trend_labels)
    assert len(flags) == 1
    assert flags[0]["excess"] == pytest.approx(0.22, abs=1e-4)
    assert flags[0]["confidence"] == "confirmed"


def test_invariant_d_buy_and_hold_against_itself_does_not_flag(monkeypatch):
    """The strategy IS the benchmark: a long-only, no-exit-ever position
    held across the whole window earns (up to slippage on the single entry
    bar) the same per-bar returns the benchmark is computed from. Excess
    must land at ~0, not at the strategy's large absolute bull share."""
    close = _two_segment_series(400, 50)  # mostly bull, by construction
    price_data = _price_data(close)

    def _buy_and_hold_returns(ir, pd_, **kwargs):
        # No fees/slippage -- isolates the invariant from the entry-bar
        # slippage cost noted in regime.py's own benchmark-derivation
        # comment, so excess lands at exactly 0, not merely close to it.
        daily_returns = pd_["Close"].pct_change()
        entries = pd.Series(False, index=pd_.index)
        entries.iloc[1] = True
        return daily_returns, entries

    monkeypatch.setattr(regime_module, "run_ir_backtest_returns", _buy_and_hold_returns)

    report = run_regime_analysis(_simple_ir(), price_data, fees=0.0, slippage=0.0)
    assert report.marginal_flags == ()


def test_marginal_flag_trips_when_strategy_is_more_bull_concentrated_than_benchmark(monkeypatch):
    """Integration-level: a strategy that earns ALL its gains in bull bars
    on a series where buy-and-hold itself earns a meaningful share of gains
    in bear bars (a bear-segment relief rally) is more bull-concentrated
    than its own benchmark, and must flag -- the scenario the old absolute
    80% threshold was trying (and over-firing) to catch."""
    close = _two_segment_series(400, 400)
    trend_labels, _ = regime_module._axis_labels(close)

    def _bull_only_returns(ir, price_data, **kwargs):
        idx = price_data.index
        bull_mask = (trend_labels == "bull").reindex(idx, fill_value=False)
        bear_mask = (trend_labels == "bear").reindex(idx, fill_value=False)
        returns = pd.Series(0.0, index=idx)
        returns[bull_mask] = 0.01
        returns[bear_mask] = -0.01  # strategy loses money in bear bars -> 0 bear gains
        entries = pd.Series(False, index=idx)
        return returns, entries

    monkeypatch.setattr(regime_module, "run_ir_backtest_returns", _bull_only_returns)

    price_data = _price_data(close)
    report = run_regime_analysis(_simple_ir(), price_data)

    assert len(report.marginal_flags) == 1
    flag = report.marginal_flags[0]
    assert flag["flag"] == "bull_concentration"
    assert flag["strategy_bull_share"] == pytest.approx(1.0, abs=1e-6)
    # The benchmark (buy-and-hold on this same two-segment series) earns
    # essentially none of its gains in the bear segment either (it's a
    # clean downtrend, not a choppy one) -- so this scenario mainly proves
    # the wiring (benchmark derived internally, real trend_labels) rather
    # than a large excess; the threshold-crossing magnitude is covered by
    # the unit-level invariant tests above.
    assert flag["benchmark_bull_share"] < flag["strategy_bull_share"]


def test_num_entries_attributed_per_regime_matches_real_entry_flags(monkeypatch):
    close = _two_segment_series(300, 300)

    def _fake_returns(ir, price_data, **kwargs):
        n = len(price_data)
        returns = pd.Series(0.0, index=price_data.index)
        entries = pd.Series(False, index=price_data.index)
        entries.iloc[10] = True  # falls in the (still-warming-up / bull) region
        entries.iloc[n - 5] = True  # falls in the bear region
        return returns, entries

    monkeypatch.setattr(regime_module, "run_ir_backtest_returns", _fake_returns)

    price_data = _price_data(close)
    report = run_regime_analysis(_simple_ir(), price_data)
    total_entries = sum(b.num_entries for b in report.breakdowns)
    assert total_entries <= 2  # one or both entries land in a labeled (non-warmup) regime
    assert total_entries >= 1
