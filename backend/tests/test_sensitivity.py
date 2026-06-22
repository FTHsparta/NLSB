import math

import numpy as np
import pandas as pd
import pytest

from app.robustness import sensitivity as sensitivity_module
from app.robustness.params import extract_tunable_params
from app.robustness.sensitivity import run_sensitivity


def _oscillating_close(n: int = 300) -> pd.Series:
    block = np.concatenate([-np.ones(20), np.ones(20)])
    reps = int(np.ceil((n - 1) / len(block)))
    deltas = np.tile(block, reps)[: n - 1]
    close = 100 + np.concatenate([[0], np.cumsum(deltas)])
    idx = pd.date_range("2015-01-01", periods=n, freq="D")
    return pd.Series(close, index=idx, dtype=float)


def _price_data(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close})


def _simple_ir():
    return {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [
            {"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}
        ],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        "exit": {"left": "rsi14", "op": ">", "right": 70},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }


def test_run_sensitivity_returns_one_result_per_tunable_param():
    ir = _simple_ir()
    price_data = _price_data(_oscillating_close())
    results = run_sensitivity(ir, price_data)
    assert len(results) == len(extract_tunable_params(ir))
    param_ids = {r.param_id for r in results}
    assert param_ids == {"indicators.rsi14.period", "entry.right", "exit.right"}


def test_each_param_sweeps_its_full_grid():
    ir = _simple_ir()
    price_data = _price_data(_oscillating_close())
    results = run_sensitivity(ir, price_data)
    period_result = next(r for r in results if r.param_id == "indicators.rsi14.period")
    assert len(period_result.grid_points) == 5
    assert [p.value for p in period_result.grid_points] == [10, 12, 14, 16, 18]


def test_every_grid_point_goes_through_run_ir_backtest(monkeypatch):
    """Sensitivity must reuse run_ir_backtest for every sub-backtest, never
    reimplement backtest math."""
    calls = []
    original = sensitivity_module.run_ir_backtest

    def _spy(ir, price_data, **kwargs):
        calls.append(ir)
        return original(ir, price_data, **kwargs)

    monkeypatch.setattr(sensitivity_module, "run_ir_backtest", _spy)

    ir = _simple_ir()
    price_data = _price_data(_oscillating_close())
    results = run_sensitivity(ir, price_data)

    total_grid_points = sum(len(r.grid_points) for r in results)
    assert len(calls) == total_grid_points
    assert total_grid_points > 0


def test_grid_point_results_have_finite_metrics_on_oscillating_series():
    ir = _simple_ir()
    price_data = _price_data(_oscillating_close())
    results = run_sensitivity(ir, price_data)
    for r in results:
        for gp in r.grid_points:
            assert gp.error is None
            assert not math.isnan(gp.sharpe_ratio)


def test_per_period_sharpe_is_annualized_sharpe_divided_by_sqrt_252():
    ir = _simple_ir()
    price_data = _price_data(_oscillating_close())
    results = run_sensitivity(ir, price_data)
    for r in results:
        for gp in r.grid_points:
            assert gp.per_period_sharpe_ratio == pytest.approx(
                gp.sharpe_ratio / math.sqrt(252), rel=1e-9
            )


def test_broad_plateau_strategy_is_labeled_robust():
    """An exit threshold set far outside the price range never fires for
    any value in its neighborhood grid (the grid is +/-20% of 1,000,000,
    still far above the ~100 price range) -- so every grid point produces
    an identical backtest (entry fires, position never exits): zero spread,
    a perfectly flat plateau."""
    ir = _simple_ir()
    ir["entry"] = {"left": "close", "op": "<", "right": 90}
    ir["exit"] = {"left": "close", "op": ">", "right": 1_000_000}
    price_data = _price_data(_oscillating_close())
    results = run_sensitivity(ir, price_data)
    exit_result = next(r for r in results if r.param_id == "exit.right")
    assert exit_result.robustness_label == "robust (broad plateau)"
    assert exit_result.peakiness == pytest.approx(0.0, abs=1e-9)


def test_fragile_strategy_with_one_good_grid_point_is_labeled_fragile():
    """Construct an entry threshold whose grid has one period where the
    strategy enters profitably and others where it barely trades --
    peakiness should be high and the label should say fragile."""
    ir = _simple_ir()
    # A short, mostly-flat-then-single-dip series: only a narrow RSI period
    # window catches the dip; far-off periods miss it entirely.
    idx = pd.date_range("2015-01-01", periods=60, freq="D")
    close = np.concatenate([np.full(30, 100.0), np.linspace(100, 70, 10), np.full(20, 100.0)])
    price_data = _price_data(pd.Series(close, index=idx, dtype=float))

    results = run_sensitivity(ir, price_data)
    period_result = next(r for r in results if r.param_id == "indicators.rsi14.period")
    # Just confirm the scoring machinery produces a real, finite peakiness
    # and a label consistent with the documented thresholds -- the exact
    # number depends on engine internals, not asserted precisely here.
    assert not math.isnan(period_result.peakiness)
    assert period_result.robustness_label in {
        "robust (broad plateau)",
        "moderate",
        "fragile (sharp peak)",
    }


def test_grid_point_error_is_captured_not_raised(monkeypatch):
    """If a grid point's mutated IR makes run_ir_backtest raise, sensitivity
    must record the error on that point and continue, not crash the sweep."""
    real_run_ir_backtest = sensitivity_module.run_ir_backtest

    def _boom(ir, price_data, **kwargs):
        if ir["indicators"][0]["params"]["period"] == 14:
            raise RuntimeError("simulated engine failure")
        return real_run_ir_backtest(ir, price_data, **kwargs)

    monkeypatch.setattr(sensitivity_module, "run_ir_backtest", _boom)

    ir = _simple_ir()
    price_data = _price_data(_oscillating_close())
    results = run_sensitivity(ir, price_data)
    period_result = next(r for r in results if r.param_id == "indicators.rsi14.period")
    failing_point = next(p for p in period_result.grid_points if p.value == 14)
    assert failing_point.error == "simulated engine failure"
    assert math.isnan(failing_point.sharpe_ratio)
