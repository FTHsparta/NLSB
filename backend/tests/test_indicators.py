import numpy as np
import pandas as pd
import pytest

from app.engine.indicators import wilder_rsi


def _reference_wilder_rsi(close: pd.Series, period: int) -> pd.Series:
    """Independent, deliberately-naive re-implementation of Wilder's RSI.

    Walks the recursive definition step by step with plain Python, as a
    second implementation to check ``wilder_rsi`` against. Used as the
    "known-good reference" required by the correctness spec.
    """
    deltas = close.diff().to_list()
    gains = [max(d, 0) if d == d else float("nan") for d in deltas]
    losses = [max(-d, 0) if d == d else float("nan") for d in deltas]

    n = len(close)
    out = [float("nan")] * n
    if n <= period:
        return pd.Series(out, index=close.index)

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    out[period] = _rsi_from_avgs(avg_gain, avg_loss)

    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i] = _rsi_from_avgs(avg_gain, avg_loss)

    return pd.Series(out, index=close.index)


def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _sample_close(n: int = 120, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.1, 1.0, n)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.Series(100 + np.cumsum(steps), index=idx)


def test_matches_independent_recursive_reference():
    close = _sample_close()
    rsi = wilder_rsi(close, period=14)
    ref = _reference_wilder_rsi(close, period=14)

    pd.testing.assert_series_equal(rsi, ref, check_names=False)


def test_first_period_values_are_nan_then_defined():
    close = _sample_close()
    rsi = wilder_rsi(close, period=14)

    assert rsi.iloc[:14].isna().all()
    assert rsi.iloc[14:].notna().all()


def test_bounded_between_0_and_100():
    close = _sample_close()
    rsi = wilder_rsi(close, period=14)

    valid = rsi.dropna()
    assert (valid >= 0).all()
    assert (valid <= 100).all()


def test_monotonically_increasing_series_saturates_at_100():
    idx = pd.date_range("2020-01-01", periods=30, freq="D")
    close = pd.Series(range(100, 130), index=idx, dtype=float)  # strictly up every bar

    rsi = wilder_rsi(close, period=14)

    assert rsi.iloc[14:].eq(100.0).all()


def test_monotonically_decreasing_series_saturates_at_0():
    idx = pd.date_range("2020-01-01", periods=30, freq="D")
    close = pd.Series(range(130, 100, -1), index=idx, dtype=float)  # strictly down every bar

    rsi = wilder_rsi(close, period=14)

    assert rsi.iloc[14:].eq(0.0).all()


def test_differs_from_naive_sma_based_rsi():
    """Requirement: Wilder's smoothing, NOT a simple moving average of gains/losses."""
    close = _sample_close()

    rsi = wilder_rsi(close, period=14)

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    naive_avg_gain = gain.rolling(window=14).mean()
    naive_avg_loss = loss.rolling(window=14).mean()
    naive_rs = naive_avg_gain / naive_avg_loss
    naive_rsi = 100 - (100 / (1 + naive_rs))

    # The seed value (index 14) is identical by construction (both are a
    # plain SMA of the first 14 gains/losses); they diverge afterwards
    # because Wilder's RSI keeps smoothing while the naive version
    # recomputes a fresh rolling SMA each bar.
    assert rsi.iloc[14] == pytest.approx(naive_rsi.iloc[14])
    assert not np.isclose(rsi.iloc[30], naive_rsi.iloc[30])
