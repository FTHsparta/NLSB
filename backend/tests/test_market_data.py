import pandas as pd
import pytest

from app.data import market_data
from app.data.market_data import InsufficientDataError, fetch_daily_bars


def _synthetic_multiindex_df(n: int, ticker: str = "SPY", freq: str = "D") -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=n, freq=freq)
    fields = ["Open", "High", "Low", "Close", "Volume"]
    columns = pd.MultiIndex.from_product([fields, [ticker]])
    data = {(f, ticker): range(n) for f in fields}
    return pd.DataFrame(data, index=idx, columns=columns)


def test_flattens_multiindex_columns_and_keeps_ohlcv(monkeypatch):
    df = _synthetic_multiindex_df(300)
    monkeypatch.setattr(market_data.yf, "download", lambda *a, **k: df)

    result = fetch_daily_bars("SPY", start="2020-01-01")

    assert list(result.columns) == market_data.OHLCV_COLUMNS
    assert not isinstance(result.columns, pd.MultiIndex)
    assert len(result) == 300


def test_empty_data_raises(monkeypatch):
    monkeypatch.setattr(market_data.yf, "download", lambda *a, **k: pd.DataFrame())

    with pytest.raises(InsufficientDataError):
        fetch_daily_bars("BOGUS", start="2020-01-01")


def test_too_few_bars_raises(monkeypatch):
    df = _synthetic_multiindex_df(10)
    monkeypatch.setattr(market_data.yf, "download", lambda *a, **k: df)

    with pytest.raises(InsufficientDataError):
        fetch_daily_bars("SPY", start="2020-01-01", min_bars=252)


def test_large_gap_raises(monkeypatch):
    # 300 daily bars, then a 30-day gap, then 300 more.
    idx1 = pd.date_range("2020-01-01", periods=300, freq="D")
    idx2 = pd.date_range(idx1[-1] + pd.Timedelta(days=31), periods=300, freq="D")
    idx = idx1.append(idx2)
    fields = ["Open", "High", "Low", "Close", "Volume"]
    columns = pd.MultiIndex.from_product([fields, ["SPY"]])
    data = {(f, "SPY"): range(len(idx)) for f in fields}
    df = pd.DataFrame(data, index=idx, columns=columns)

    monkeypatch.setattr(market_data.yf, "download", lambda *a, **k: df)

    with pytest.raises(InsufficientDataError):
        fetch_daily_bars("SPY", start="2020-01-01")


@pytest.mark.live
def test_real_spy_fetch_is_clean():
    """Integration check against live yfinance — exercises the real network path.
    Marked `live` so CI (which has no stable network path to Yahoo) skips it;
    it still runs in the default local suite."""
    df = fetch_daily_bars("SPY", start="2015-01-01", end="2024-01-01")

    assert list(df.columns) == market_data.OHLCV_COLUMNS
    assert df.index.is_monotonic_increasing
    assert df["Close"].notna().all()
    assert len(df) > 2000
