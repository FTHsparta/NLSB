"""Technical indicators for the backtest engine.

Correctness requirement: RSI must use **Wilder's smoothing**, matching the
convention used by TradingView and most retail platforms — NOT a simple
moving average of gains/losses.

SMA: standard rolling window mean (rolling(period).mean()).
EMA: exponential moving average with alpha = 2/(period+1), no SMA seed
     (pandas ewm default with adjust=False). First bar is the raw price;
     the series converges within ~3*period bars.
"""

import numpy as np
import pandas as pd


def wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI.

    Average gain/loss is seeded with a simple moving average of the first
    ``period`` price changes, then smoothed recursively:
    ``avg[i] = (avg[i-1] * (period - 1) + value[i]) / period``.

    This is the "RMA" convention (``rma[0] = sma(src, period)``, then
    exponential smoothing with ``alpha = 1/period``) — the same one
    TradingView's ``ta.rma()`` / built-in RSI uses, and differs from naively
    computing ``rolling(period).mean()`` for gains and losses at every bar.

    The first ``period`` values are NaN (no signal can be computed there);
    the first defined RSI value is at index ``period``.
    """
    if period < 1:
        raise ValueError("period must be >= 1")

    delta = close.diff()
    gain = delta.clip(lower=0).to_numpy()
    loss = (-delta.clip(upper=0)).to_numpy()

    n = len(close)
    avg_gain = np.full(n, np.nan)
    avg_loss = np.full(n, np.nan)

    if n <= period:
        return pd.Series(np.nan, index=close.index)

    avg_gain[period] = gain[1 : period + 1].mean()
    avg_loss[period] = loss[1 : period + 1].mean()

    for i in range(period + 1, n):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period

    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    # avg_gain == 0 and avg_loss == 0: no movement at all -> neutral.
    rsi = np.where((avg_gain == 0) & (avg_loss == 0), 50.0, rsi)
    # avg_loss == 0 and avg_gain > 0: pure up-streak -> RSI saturates at 100.
    rsi = np.where((avg_gain > 0) & (avg_loss == 0), 100.0, rsi)

    return pd.Series(rsi, index=close.index)


def sma(close: pd.Series, period: int) -> pd.Series:
    """Simple moving average (rolling window mean).

    Returns NaN for the first ``period - 1`` bars; first defined value is at
    index ``period - 1``.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    return close.rolling(window=period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    """Exponential moving average with alpha = 2/(period+1).

    Uses pandas ewm(span=period, adjust=False) — no SMA seed, first value
    equals the first bar's price. Converges to the "true" EMA within ~3*period
    bars.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    return close.ewm(span=period, adjust=False).mean()
