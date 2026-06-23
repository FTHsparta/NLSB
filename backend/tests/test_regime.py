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
# Marginal concentration (per-axis) -- catches bull/bear- or vol-dependence
# that the 2x2 cell view can mask by splitting gains across two cells that
# agree on one axis.
# ---------------------------------------------------------------------------


def test_bull_dependence_marginal_flag_trips_when_cell_flag_stays_silent(monkeypatch):
    """The canonical '2020-21 bull run' shape: gains land in BOTH bull
    cells (crash-recover high-vol + grind-up low-vol), losses in BOTH bear
    cells. Neither single cell owns 80% of the gains, so the per-cell flag
    must stay silent -- but the trend MARGINAL (bull vs bear, ignoring vol)
    owns ~100% and must trip."""
    close = _two_segment_series(400, 400)
    trend_labels, vol_labels = regime_module._axis_labels(close)
    labels = regime_module._combine_labels(trend_labels, vol_labels)

    def _fake_returns(ir, price_data, **kwargs):
        idx = price_data.index
        bull_mask = (trend_labels == "bull").reindex(idx, fill_value=False)
        bear_mask = (trend_labels == "bear").reindex(idx, fill_value=False)
        returns = pd.Series(0.0, index=idx)
        returns[bull_mask] = 0.01  # split across bull_high_vol AND bull_low_vol
        returns[bear_mask] = -0.01  # split across bear_high_vol AND bear_low_vol
        entries = pd.Series(False, index=idx)
        return returns, entries

    monkeypatch.setattr(regime_module, "run_ir_backtest_returns", _fake_returns)

    price_data = _price_data(close)
    report = run_regime_analysis(_simple_ir(), price_data)

    # Per-cell flag stays silent: gains split roughly 50/50 across the two
    # bull cells (whatever the exact vol-median split happens to be).
    assert report.concentrated_regime is None
    assert report.concentration_share is None

    # Trend marginal flag trips for "bull".
    trend_flags = [f for f in report.marginal_flags if f.axis == "trend"]
    assert len(trend_flags) == 1
    assert trend_flags[0].dominant_label == "bull"
    assert trend_flags[0].share >= regime_module.MARGINAL_CONCENTRATION_SHARE_THRESHOLD
    assert trend_flags[0].dependence_label == "bull-dependent"


def test_no_marginal_flag_when_gains_are_spread_across_both_axis_sides(monkeypatch):
    close = _two_segment_series(400, 400)

    def _fake_returns(ir, price_data, **kwargs):
        returns = pd.Series(0.005, index=price_data.index)  # uniform everywhere
        entries = pd.Series(False, index=price_data.index)
        return returns, entries

    monkeypatch.setattr(regime_module, "run_ir_backtest_returns", _fake_returns)

    price_data = _price_data(close)
    report = run_regime_analysis(_simple_ir(), price_data)
    assert report.marginal_flags == ()


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
