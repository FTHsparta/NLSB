import numpy as np
import pandas as pd

from app.engine.backtest import run_rsi_backtest


def _oscillating_close(n: int = 200) -> pd.Series:
    """A price series that swings sharply enough to push RSI(14) through
    both the 30 and 70 thresholds multiple times, so the strategy actually
    trades."""
    block = np.concatenate([-np.ones(20), np.ones(20)])  # 40-day down/up cycle
    reps = int(np.ceil((n - 1) / len(block)))
    deltas = np.tile(block, reps)[: n - 1]
    close = 100 + np.concatenate([[0], np.cumsum(deltas)])
    idx = pd.date_range("2015-01-01", periods=n, freq="D")
    return pd.Series(close, index=idx, dtype=float)


def test_oscillating_series_produces_trades():
    close = _oscillating_close()
    result = run_rsi_backtest(close)

    assert result.num_trades > 0


def test_warmup_window_drops_first_period_plus_one_bars():
    close = _oscillating_close()
    rsi_period = 14
    result = run_rsi_backtest(close, rsi_period=rsi_period)

    expected_start = close.index[rsi_period + 1]
    assert result.start == str(expected_start.date())
    assert result.end == str(close.index[-1].date())


def test_costs_reduce_returns_relative_to_no_cost_baseline():
    close = _oscillating_close()

    no_cost = run_rsi_backtest(close, fees=0.0, slippage=0.0)
    with_cost = run_rsi_backtest(close, fees=0.001, slippage=0.001)

    assert no_cost.num_trades > 0
    assert with_cost.total_return < no_cost.total_return


def test_flat_series_produces_no_trades_and_nan_win_rate():
    idx = pd.date_range("2020-01-01", periods=50, freq="D")
    close = pd.Series(100.0, index=idx)

    result = run_rsi_backtest(close)

    assert result.num_trades == 0
    assert result.total_return == 0.0
    assert result.win_rate != result.win_rate  # NaN
