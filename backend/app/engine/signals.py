"""Signal generation and the no-lookahead execution convention.

Correctness requirement: a signal computed from bar ``i``'s close must not
be acted on at bar ``i``'s close (that would be foresight). This engine's
convention is **signal at close[i] -> execute at close[i+1]** — every raw
condition is shifted forward by one bar via :func:`shift_for_next_bar_execution`
before being handed to vectorbt (which fills at the same bar's close by
default).
"""

import pandas as pd


def rsi_threshold_signals(
    rsi: pd.Series, lower: float, upper: float
) -> tuple[pd.Series, pd.Series]:
    """Raw, same-bar conditions: RSI below ``lower`` -> entry, above ``upper`` -> exit.

    These are *not* execution-ready — pass through
    :func:`shift_for_next_bar_execution` first.
    """
    entries = (rsi < lower).fillna(False)
    exits = (rsi > upper).fillna(False)
    return entries, exits


def shift_for_next_bar_execution(signal: pd.Series) -> pd.Series:
    """Shift a same-bar signal so it becomes actionable on the *next* bar.

    Bar 0 can never carry a shifted-in signal, so it is always False.
    """
    return signal.shift(1, fill_value=False)
