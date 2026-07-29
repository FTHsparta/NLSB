"""Market data fetching + validation (requirement: survivorship/data sanity).

v1 only needs daily equity/ETF bars via yfinance. Adjusted close (splits,
dividends) is used throughout via ``auto_adjust=True``.

Phase 12B added the guard this module was missing. The four checks that came
before it -- empty frame, minimum bar count, maximum internal gap, and the
downstream runnable-window check -- are all *internal-consistency* checks:
each one asks whether the returned data is self-consistent, and none of them
ever asked whether it is the data that was REQUESTED. A request for 2015-2026
answered with a clean, gapless, 1500-bar 2015-2020 frame passed all four and
silently ran on six years instead of eleven. `enforce_coverage` closes that:
it compares the realized index against the requested range and refuses rather
than clamping. Silently narrowing a window is the exact failure this exists
to remove.

Every knob reads its environment variable at call time, matching the NLSB_*
config style used in `app.abuse`.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import OrderedDict

import pandas as pd
import yfinance as yf

logger = logging.getLogger("app.data.market_data")

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


class InsufficientDataError(ValueError):
    """Raised when fetched data is missing, too short, has suspicious gaps, or
    does not cover the range that was asked for."""


# --- Config -----------------------------------------------------------------


def yfinance_timeout_seconds() -> float:
    """Per-attempt network timeout. yfinance 1.4.1's `download()` takes this
    directly, so no wrapper layer is needed."""
    return float(os.environ.get("NLSB_YFINANCE_TIMEOUT_SECONDS", "30"))


def yfinance_max_retries() -> int:
    """Retries AFTER the first attempt, so the default of 2 means at most 3
    attempts. Worst-case wall time is bounded and stated in LOG.md."""
    return int(os.environ.get("NLSB_YFINANCE_MAX_RETRIES", "2"))


def coverage_tolerance_days_start() -> int:
    """Slack at the leading edge: a requested start landing on a weekend or a
    market holiday legitimately yields a first bar a few days later."""
    return int(os.environ.get("NLSB_COVERAGE_TOLERANCE_DAYS_START", "7"))


def coverage_tolerance_days_end() -> int:
    """Slack at the trailing edge, absorbing vendor lag on recent bars."""
    return int(os.environ.get("NLSB_COVERAGE_TOLERANCE_DAYS_END", "7"))


def price_cache_enabled() -> bool:
    return os.environ.get("NLSB_PRICE_CACHE_ENABLED", "true").lower() == "true"


def price_cache_size() -> int:
    return int(os.environ.get("NLSB_PRICE_CACHE_SIZE", "64"))


# --- Realized window --------------------------------------------------------


def _iso_date(value: object) -> str | None:
    if value is None:
        return None
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(stamp):
        return None
    return stamp.date().isoformat()


def realized_window(
    frame: pd.DataFrame,
    requested_start: object = None,
    requested_end: object = None,
) -> dict:
    """The window a backtest actually ran on, as plain JSON-safe values.

    A pure function of the frame's index plus what was asked for, which is
    what makes a cache hit report identically to a fresh fetch: there is no
    stored state that could disagree with the data.

    `requested_end` is legitimately None -- "from this date to whatever exists"
    is a normal request -- and is reported as None rather than guessed at.
    """
    index = frame.index
    return {
        "realized_start": _iso_date(index.min()) if len(index) else None,
        "realized_end": _iso_date(index.max()) if len(index) else None,
        "bar_count": int(len(index)),
        "requested_start": _iso_date(requested_start),
        "requested_end": _iso_date(requested_end),
    }


def enforce_coverage(
    frame: pd.DataFrame,
    ticker: str,
    requested_start: object,
    requested_end: object,
) -> None:
    """Refuse a frame that falls short of the requested range at either end.

    Deliberately a REFUSAL and never a clamp. A ticker that simply did not
    exist yet is not a bug -- but it is also not something to paper over, so
    the message names both windows and lets the caller re-ask with real dates.
    Quietly answering a different question than the one asked is the failure
    mode this whole module now exists to prevent.
    """
    if not len(frame.index):  # the empty-frame guard already covers this
        return

    first = pd.Timestamp(frame.index.min()).normalize()
    last = pd.Timestamp(frame.index.max()).normalize()
    available = f"{first.date().isoformat()} to {last.date().isoformat()}"

    start = pd.Timestamp(requested_start).normalize() if requested_start else None
    if start is not None:
        shortfall = (first - start).days
        if shortfall > coverage_tolerance_days_start():
            raise InsufficientDataError(
                f"{ticker!r} has no price data before {first.date().isoformat()}, but you "
                f"asked for history starting {start.date().isoformat()}. Available data: "
                f"{available}. Re-run with a start date on or after "
                f"{first.date().isoformat()}."
            )

    end = pd.Timestamp(requested_end).normalize() if requested_end else None
    if end is not None:
        shortfall = (end - last).days
        if shortfall > coverage_tolerance_days_end():
            raise InsufficientDataError(
                f"{ticker!r} has no price data after {last.date().isoformat()}, but you "
                f"asked for history through {end.date().isoformat()}. Available data: "
                f"{available}. Re-run with an end date on or before "
                f"{last.date().isoformat()}."
            )


# --- Bounded price cache ----------------------------------------------------


class PriceCache:
    """Thread-safe bounded LRU of VALIDATED frames.

    Same shape as the Phase 12A translation cache and for the same two
    reasons: route handlers are sync `def` and run in anyio's thread pool, so
    every operation is genuinely concurrent; and the bound is a security
    property, not a tuning knob -- an unbounded map keyed on user-supplied
    tickers and dates is a memory-exhaustion primitive.

    Only frames that passed EVERY guard are ever stored, so a hit can never
    resurrect an empty frame, a short frame, or one that failed coverage.
    """

    def __init__(self) -> None:
        self._entries: OrderedDict[tuple, pd.DataFrame] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple) -> pd.DataFrame | None:
        if not price_cache_enabled():
            return None
        with self._lock:
            if key not in self._entries:
                return None
            self._entries.move_to_end(key)
            frame = self._entries[key]
        # A copy, never the shared frame: the engine and the sensitivity sweep
        # both index into this, and one mutation would poison every later hit.
        return frame.copy(deep=True)

    def put(self, key: tuple, frame: pd.DataFrame) -> None:
        if not price_cache_enabled():
            return
        stored = frame.copy(deep=True)
        limit = max(0, price_cache_size())
        with self._lock:
            if limit == 0:
                return
            self._entries[key] = stored
            self._entries.move_to_end(key)
            while len(self._entries) > limit:
                evicted, _ = self._entries.popitem(last=False)
                logger.debug("price cache evicted %r (size limit %d)", evicted, limit)

    def clear(self) -> None:
        """For tests only: the cache is process-global."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


price_cache = PriceCache()


def _cache_key(ticker: str, start: object, end: object, interval: str) -> tuple:
    return (str(ticker), _iso_date(start), _iso_date(end), interval)


# --- Fetch ------------------------------------------------------------------


def _download_with_retry(ticker: str, start: object, end: object, interval: str):
    """One bounded retry loop around the network call.

    Retries TRANSPORT failures only. A frame that comes back and fails a
    validation guard is not retried -- the answer would be the same, and
    burning the retry budget on it just delays a 422 the caller can act on.
    """
    attempts = max(0, yfinance_max_retries()) + 1
    timeout = yfinance_timeout_seconds()
    last_exc: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return yf.download(
                ticker,
                start=start,
                end=end,
                interval=interval,
                progress=False,
                auto_adjust=True,
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001 -- provider/transport errors vary
            last_exc = exc
            if attempt == attempts:
                break
            backoff = 0.5 * (2 ** (attempt - 1))
            logger.warning(
                "price fetch for %r failed (attempt %d/%d): %s; retrying in %.1fs",
                ticker,
                attempt,
                attempts,
                exc,
                backoff,
            )
            time.sleep(backoff)

    assert last_exc is not None
    raise last_exc


def fetch_daily_bars(
    ticker: str,
    start: str,
    end: str | None = None,
    min_bars: int = 252,
    max_gap_days: int = 10,
    interval: str = "1d",
) -> pd.DataFrame:
    """Fetch and validate daily OHLCV bars for ``ticker``.

    Raises ``InsufficientDataError`` if the ticker has no data, fewer than
    ``min_bars`` rows, a gap larger than ``max_gap_days`` (a sign of a
    delisting, bad ticker, or other data quality issue), or -- new in Phase
    12B -- if the data does not actually cover the requested range.

    Returns a plain DataFrame, unchanged from before: the realized window is a
    pure function of the returned index (see `realized_window`), so callers
    and fakes need no new return shape to report it.
    """
    key = _cache_key(ticker, start, end, interval)
    cached = price_cache.get(key)
    if cached is not None:
        logger.info("price cache hit for %r", key)
        return cached

    df = _download_with_retry(ticker, start, end, interval)

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

    # Last, so a frame is only ever cached once it has cleared every guard
    # INCLUDING coverage. Nothing that failed is remembered.
    enforce_coverage(df, ticker, start, end)

    price_cache.put(key, df)
    return df
