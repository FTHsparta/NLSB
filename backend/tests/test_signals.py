import pandas as pd
import vectorbt as vbt

from app.engine.signals import rsi_threshold_signals, shift_for_next_bar_execution


def test_shift_moves_signal_to_next_bar():
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    raw = pd.Series(False, index=idx)
    raw.iloc[3] = True
    raw.iloc[7] = True

    shifted = shift_for_next_bar_execution(raw)

    assert shifted.iloc[4]
    assert shifted.iloc[8]
    # original positions are no longer set
    assert not shifted.iloc[3]
    assert not shifted.iloc[7]
    # bar 0 can never inherit a shifted-in signal
    assert not shifted.iloc[0]
    assert shifted.sum() == raw.sum()


def test_rsi_threshold_signals_have_no_nan_and_match_conditions():
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    rsi = pd.Series([float("nan"), 25.0, 50.0, 75.0, 29.9], index=idx)

    entries, exits = rsi_threshold_signals(rsi, lower=30, upper=70)

    assert entries.tolist() == [False, True, False, False, True]
    assert exits.tolist() == [False, False, False, True, False]
    assert entries.dtype == bool
    assert exits.dtype == bool


def test_no_lookahead_entry_executes_on_bar_after_signal():
    """A signal computed from bar i's close must fill at bar i+1's close, not bar i's."""
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    # Distinct closes so we can tell which bar an order filled at.
    close = pd.Series([10, 11, 5, 13, 14, 15, 16, 17, 18, 19], index=idx, dtype=float)

    # Pretend RSI dropped below 30 on bar 2 (close=5) -> raw entry condition at index 2.
    raw_entries = pd.Series(False, index=idx)
    raw_entries.iloc[2] = True
    raw_exits = pd.Series(False, index=idx)

    entries = shift_for_next_bar_execution(raw_entries)
    exits = shift_for_next_bar_execution(raw_exits)

    pf = vbt.Portfolio.from_signals(close, entries, exits, fees=0.0, slippage=0.0, init_cash=1000)
    trades = pf.trades.records_readable

    assert len(trades) == 1
    fill_timestamp = trades["Entry Timestamp"].iloc[0]
    fill_price = trades["Avg Entry Price"].iloc[0]

    # The signal was "computed" from bar index 2's close (5) -- if it had
    # executed at that same bar (lookahead), the fill price would be 5.
    # The no-lookahead convention fills at bar index 3's close (13) instead.
    assert fill_timestamp == idx[3]
    assert fill_price == close.iloc[3]
    assert fill_price != close.iloc[2]
