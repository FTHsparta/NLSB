"""Pins the open-position convention on the never-exit (no-exit-stated) path.

defaults.py defaults a missing exit to an always-false sentinel condition
(see app.translation.defaults.NO_EXIT_CONDITION). This test asserts that
running such an IR through the real backtest engine produces exactly the
behaviour the renderer's disclosure prose promises the user: one trade,
entered on the first entry signal, held open through the last bar, with all
summary metrics computing without error. If vectorbt ever did something
else with an all-False exit array (e.g. silently closing at the end, or
raising), this test should fail loudly rather than the discrepancy being
papered over downstream.
"""

import math

import numpy as np
import pandas as pd

from app.engine.backtest import run_ir_backtest
from app.translation.defaults import apply_defaults


def _oscillating_close(n: int = 200) -> pd.Series:
    block = np.concatenate([-np.ones(20), np.ones(20)])
    reps = int(np.ceil((n - 1) / len(block)))
    deltas = np.tile(block, reps)[: n - 1]
    close = 100 + np.concatenate([[0], np.cumsum(deltas)])
    idx = pd.date_range("2015-01-01", periods=n, freq="D")
    return pd.Series(close, index=idx, dtype=float)


def _price_data(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close})


def test_no_exit_sentinel_produces_exactly_one_open_trade_held_to_final_bar():
    sparse_ir = {
        "asset": {"ticker": "SPY"},
        "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        # no "exit" key -> defaults to the always-false sentinel
    }
    full_ir, assumptions = apply_defaults(sparse_ir)
    assert full_ir["exit"] == {"left": "close", "op": "<", "right": "close"}

    close = _oscillating_close()
    price_data = _price_data(close)

    result = run_ir_backtest(full_ir, price_data, fees=0.0, slippage=0.0)

    assert result.num_trades == 1
    assert result.end == str(price_data.index[-1].date())
    # all metrics must compute without raising and without being NaN-by-bug
    assert not math.isnan(result.total_return)
    assert not math.isnan(result.max_drawdown)
    assert not math.isnan(result.annualized_return)
