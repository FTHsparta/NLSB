"""Market data fetching + validation (requirement: survivorship/data sanity).

v1 only needs daily equity/ETF bars via yfinance. Adjusted close (splits,
dividends) is used throughout via ``auto_adjust=True``.
"""

import pandas as pd
import yfinance as yf

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


class InsufficientDataError(ValueError):
    """Raised when fetched data is missing, too short, or has suspicious gaps."""


def fetch_daily_bars(
    ticker: str,
    start: str,
    end: str | None = None,
    min_bars: int = 252,
    max_gap_days: int = 10,
) -> pd.DataFrame:
    """Fetch and validate daily OHLCV bars for ``ticker``.

    Raises ``InsufficientDataError`` if the ticker has no data, fewer than
    ``min_bars`` rows, or a gap larger than ``max_gap_days`` (a sign of a
    delisting, bad ticker, or other data quality issue).
    """
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)

    if df is None or df.empty:
        raise InsufficientDataError(f"No data returned for {ticker!r}")

    # Recent yfinance versions return MultiIndex columns (field, ticker) even
    # for a single ticker — flatten to a plain OHLCV frame.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[OHLCV_COLUMNS].copy()
    df = df.dropna(subset=["Close"])
    df = df.sort_index()

    if len(df) < min_bars:
        raise InsufficientDataError(
            f"{ticker!r} has only {len(df)} bars, need at least {min_bars}"
        )

    gaps = df.index.to_series().diff().dropna()
    max_gap = gaps.max()
    if max_gap > pd.Timedelta(days=max_gap_days):
        raise InsufficientDataError(
            f"{ticker!r} has a {max_gap} gap in its price history "
            f"(max allowed: {max_gap_days} days) — data looks unreliable"
        )

    return df
