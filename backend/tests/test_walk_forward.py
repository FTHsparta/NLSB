import math

import numpy as np
import pandas as pd
import pytest

from app.engine.backtest import BacktestResult
from app.robustness import walk_forward as wf_module
from app.robustness.walk_forward import run_ir_backtest, run_walk_forward


def _oscillating_close(n: int) -> pd.Series:
    block = np.concatenate([-np.ones(20), np.ones(20)])
    reps = int(np.ceil((n - 1) / len(block)))
    deltas = np.tile(block, reps)[: n - 1]
    close = 100 + np.concatenate([[0], np.cumsum(deltas)])
    idx = pd.date_range("2015-01-01", periods=n, freq="D")
    return pd.Series(close, index=idx, dtype=float)


def _price_data(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close})


def _simple_ir():
    """2 tunables (period, entry threshold); exit is the always-false
    sentinel, so exit contributes no tunable -- keeps the grid search small
    (5*5=25 combos) for real (non-stubbed) test runs."""
    return {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [
            {"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}
        ],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        "exit": {"left": "close", "op": "<", "right": "close"},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }


# ---------------------------------------------------------------------------
# Real run_ir_backtest, small single-fold scenarios (data-sensitivity matters)
# ---------------------------------------------------------------------------


def test_fold_boundaries_are_strictly_sequential_and_non_overlapping():
    ir = _simple_ir()
    price_data = _price_data(_oscillating_close(120))
    result = run_walk_forward(ir, price_data, in_sample_bars=40, out_of_sample_bars=20, step_bars=20)
    assert len(result.folds) >= 2
    for fold in result.folds:
        assert pd.Timestamp(fold.is_end) < pd.Timestamp(fold.oos_start)
        assert pd.Timestamp(fold.oos_start) <= pd.Timestamp(fold.oos_end)


def test_chosen_params_do_not_depend_on_out_of_sample_data():
    """Same IS slice, two wildly different OOS slices -> identical chosen_params."""
    ir = _simple_ir()
    is_close = _oscillating_close(40)
    oos_idx = pd.date_range(is_close.index[-1] + pd.Timedelta(days=1), periods=20, freq="D")

    oos_close_a = pd.Series(np.full(20, 100.0), index=oos_idx)
    oos_close_b = pd.Series(np.linspace(200, 5, 20), index=oos_idx)  # wildly different

    price_data_a = _price_data(pd.concat([is_close, oos_close_a]))
    price_data_b = _price_data(pd.concat([is_close, oos_close_b]))

    result_a = run_walk_forward(ir, price_data_a, in_sample_bars=40, out_of_sample_bars=20, step_bars=20)
    result_b = run_walk_forward(ir, price_data_b, in_sample_bars=40, out_of_sample_bars=20, step_bars=20)

    assert result_a.folds[0].chosen_params == result_b.folds[0].chosen_params


def test_oos_result_matches_independent_standalone_backtest_on_same_window():
    """Confirms warmup/state doesn't bleed across the fold boundary: the
    frozen OOS backtest run inside walk-forward must equal calling
    run_ir_backtest directly on the OOS slice alone."""
    ir = _simple_ir()
    price_data = _price_data(_oscillating_close(60))
    result = run_walk_forward(ir, price_data, in_sample_bars=40, out_of_sample_bars=20, step_bars=20)
    fold = result.folds[0]

    frozen_ir = dict(ir)
    frozen_ir["indicators"] = [
        {**ir["indicators"][0], "params": {"period": fold.chosen_params["indicators.rsi14.period"]}}
    ]
    frozen_ir["entry"] = {**ir["entry"], "right": fold.chosen_params["entry.right"]}

    oos_slice = price_data.iloc[40:60]
    standalone = run_ir_backtest(frozen_ir, oos_slice, fees=wf_module.RETAIL_FEES, slippage=wf_module.RETAIL_SLIPPAGE)

    if math.isnan(standalone.sharpe_ratio):
        assert math.isnan(fold.oos_sharpe)
    else:
        assert fold.oos_sharpe == pytest.approx(standalone.sharpe_ratio)
    assert fold.oos_num_trades == standalone.num_trades


# ---------------------------------------------------------------------------
# Stubbed run_ir_backtest: fast, deterministic, structural checks
# ---------------------------------------------------------------------------


def _make_stub(score_fn, call_log=None):
    def _stub(ir, price_data, fees=0.0, slippage=0.0):
        if call_log is not None:
            call_log.append({"fees": fees, "slippage": slippage, "ir": ir, "n_bars": len(price_data)})
        period = ir["indicators"][0]["params"]["period"]
        threshold = ir["entry"]["right"]
        sharpe, num_trades = score_fn(period, threshold)
        return BacktestResult(
            total_return=0.1,
            annualized_return=0.1,
            sharpe_ratio=sharpe,
            max_drawdown=-0.05,
            win_rate=0.6,
            num_trades=num_trades,
            start=str(price_data.index[0].date()),
            end=str(price_data.index[-1].date()),
        )

    return _stub


def test_costs_are_passed_to_every_backtest_call(monkeypatch):
    calls = []
    monkeypatch.setattr(wf_module, "run_ir_backtest", _make_stub(lambda p, t: (1.0, 5), calls))

    ir = _simple_ir()
    price_data = _price_data(_oscillating_close(80))
    run_walk_forward(ir, price_data, in_sample_bars=40, out_of_sample_bars=20, step_bars=20)

    assert len(calls) > 0
    for call in calls:
        assert call["fees"] == wf_module.RETAIL_FEES
        assert call["slippage"] == wf_module.RETAIL_SLIPPAGE
        assert call["slippage"] != 0.0  # costs are actually modeled, not a no-op


def test_full_grid_is_evaluated_every_fold(monkeypatch):
    calls = []
    monkeypatch.setattr(wf_module, "run_ir_backtest", _make_stub(lambda p, t: (1.0, 5), calls))

    ir = _simple_ir()
    price_data = _price_data(_oscillating_close(80))
    result = run_walk_forward(ir, price_data, in_sample_bars=40, out_of_sample_bars=20, step_bars=20)

    # 25 IS candidates + 1 OOS call, per fold
    assert len(calls) == len(result.folds) * 26


def test_tie_breaking_prefers_stated_value_then_is_deterministic(monkeypatch):
    def flat_score(period, threshold):
        return 1.0, 10  # every candidate ties exactly

    monkeypatch.setattr(wf_module, "run_ir_backtest", _make_stub(flat_score))

    ir = _simple_ir()
    price_data = _price_data(_oscillating_close(80))
    result_1 = run_walk_forward(ir, price_data, in_sample_bars=40, out_of_sample_bars=20, step_bars=20)
    result_2 = run_walk_forward(ir, price_data, in_sample_bars=40, out_of_sample_bars=20, step_bars=20)

    assert result_1.folds[0].chosen_params == result_2.folds[0].chosen_params
    # all tied -> tie-break picks the stated value exactly
    assert result_1.folds[0].chosen_params == {"indicators.rsi14.period": 14, "entry.right": 30}


def test_low_trade_count_fold_is_flagged_low_confidence(monkeypatch):
    monkeypatch.setattr(wf_module, "run_ir_backtest", _make_stub(lambda p, t: (2.0, 3)))  # 3 < default min 10

    ir = _simple_ir()
    price_data = _price_data(_oscillating_close(80))
    result = run_walk_forward(ir, price_data, in_sample_bars=40, out_of_sample_bars=20, step_bars=20)

    assert all(fold.low_confidence for fold in result.folds)


def test_high_trade_count_fold_is_not_flagged_low_confidence(monkeypatch):
    monkeypatch.setattr(wf_module, "run_ir_backtest", _make_stub(lambda p, t: (2.0, 50)))

    ir = _simple_ir()
    price_data = _price_data(_oscillating_close(80))
    result = run_walk_forward(ir, price_data, in_sample_bars=40, out_of_sample_bars=20, step_bars=20)

    assert all(not fold.low_confidence for fold in result.folds)


def test_aggregate_degradation_is_is_minus_oos_sharpe(monkeypatch):
    """IS always scores 5.0 (best candidate found), OOS (frozen, separate
    call sequence) always scores 1.0 -- aggregate degradation must be 4.0."""
    call_counter = {"n": 0}

    def _stub(ir, price_data, fees=0.0, slippage=0.0):
        call_counter["n"] += 1
        # Within a fold: 25 IS calls then 1 OOS call. OOS gets a fixed lower score.
        is_oos_call_index = (call_counter["n"] - 1) % 26
        sharpe = 1.0 if is_oos_call_index == 25 else 5.0
        return BacktestResult(
            total_return=0.1,
            annualized_return=0.1,
            sharpe_ratio=sharpe,
            max_drawdown=-0.05,
            win_rate=0.6,
            num_trades=20,
            start=str(price_data.index[0].date()),
            end=str(price_data.index[-1].date()),
        )

    monkeypatch.setattr(wf_module, "run_ir_backtest", _stub)

    ir = _simple_ir()
    price_data = _price_data(_oscillating_close(120))
    result = run_walk_forward(ir, price_data, in_sample_bars=40, out_of_sample_bars=20, step_bars=20)

    assert result.aggregate_is_sharpe == pytest.approx(5.0)
    assert result.aggregate_oos_sharpe == pytest.approx(1.0)
    assert result.degradation == pytest.approx(4.0)


def test_a_failing_candidate_does_not_crash_the_fold(monkeypatch):
    def _stub(ir, price_data, fees=0.0, slippage=0.0):
        period = ir["indicators"][0]["params"]["period"]
        if period == 18:
            raise RuntimeError("simulated engine failure on this candidate")
        return BacktestResult(
            total_return=0.1,
            annualized_return=0.1,
            sharpe_ratio=3.0,
            max_drawdown=-0.05,
            win_rate=0.6,
            num_trades=15,
            start=str(price_data.index[0].date()),
            end=str(price_data.index[-1].date()),
        )

    monkeypatch.setattr(wf_module, "run_ir_backtest", _stub)

    ir = _simple_ir()
    price_data = _price_data(_oscillating_close(80))
    result = run_walk_forward(ir, price_data, in_sample_bars=40, out_of_sample_bars=20, step_bars=20)

    assert len(result.folds) > 0
    for fold in result.folds:
        assert fold.chosen_params["indicators.rsi14.period"] != 18
