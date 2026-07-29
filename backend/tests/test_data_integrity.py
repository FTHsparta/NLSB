"""Phase 12B: data integrity and realized-window honesty.

The four guards that existed before this phase -- empty frame, minimum bar
count, maximum internal gap, and the runnable-window check -- all asked
whether the returned data was self-consistent. Not one of them asked whether
it was the data that had been REQUESTED, so a clean frame covering half the
requested range passed every check and the result never mentioned it.

What is pinned here:
  * every result path reports the window it actually ran on, including the
    no-exit and untestable paths;
  * a frame that falls short of the requested range is REFUSED, never
    silently clamped;
  * the effective-bar floor sits where the statistics stop being degenerate;
  * the price fetch is bounded in time, bounded in retries, and cached
    without ever remembering a failure.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app import main
from app.data import market_data
from app.data.market_data import (
    InsufficientDataError,
    fetch_daily_bars,
    price_cache,
    realized_window,
)
from app.robustness.robustness import RESULT_KEYS
from app.translation import service
from app.translation.service import MIN_EFFECTIVE_BARS


def _frame(start: str, periods: int, freq: str = "B") -> pd.DataFrame:
    """Business-day bars, so weekend gaps look like real market data."""
    idx = pd.date_range(start, periods=periods, freq=freq)
    close = pd.Series(100 + np.arange(periods, dtype=float), index=idx)
    return pd.DataFrame(
        {"Open": close, "High": close, "Low": close, "Close": close, "Volume": close}
    )


def _multiindex(frame: pd.DataFrame, ticker: str = "SPY") -> pd.DataFrame:
    """yfinance hands back MultiIndex columns even for one ticker."""
    out = frame.copy()
    out.columns = pd.MultiIndex.from_product([list(frame.columns), [ticker]])
    return out


@pytest.fixture
def fake_download(monkeypatch):
    """Patch the network call; return a recorder so tests can count fetches."""
    calls = {"n": 0, "kwargs": []}

    def _install(frame_or_exc):
        def _download(*args, **kwargs):
            calls["n"] += 1
            calls["kwargs"].append(kwargs)
            if isinstance(frame_or_exc, Exception):
                raise frame_or_exc
            return frame_or_exc

        monkeypatch.setattr(market_data.yf, "download", _download)
        return calls

    return _install


# --- TASK 1: the realized window is reported, always -------------------------


def test_window_is_part_of_the_result_schema():
    assert "window" in RESULT_KEYS


def test_realized_window_reports_both_what_was_asked_and_what_was_judged():
    frame = _frame("2015-01-05", 300)
    window = realized_window(frame, "2015-01-01", "2016-12-31")

    assert window["realized_start"] == "2015-01-05"
    assert window["realized_end"] == frame.index.max().date().isoformat()
    assert window["bar_count"] == 300
    assert window["requested_start"] == "2015-01-01"
    assert window["requested_end"] == "2016-12-31"


def test_realized_window_reports_an_absent_end_as_none_rather_than_guessing():
    # "from this date to whatever exists" is a normal request.
    window = realized_window(_frame("2015-01-05", 10), "2015-01-01", None)
    assert window["requested_end"] is None
    assert window["realized_end"] is not None


@pytest.mark.parametrize(
    "builder_name",
    [
        "build_pass",
        "build_shaky",
        "build_likely_overfit",
        "build_untestable",
        "build_no_exit",
        "build_bull_concentration_confirmed",
        "build_bull_concentration_provisional",
        "build_bull_concentration_with_verdict",
    ],
)
def test_every_result_kind_reports_its_window(builder_name):
    """INV: no backtest runs on a window it does not report. Walks every
    fixture kind, including no_exit (which short-circuits before the robustness
    machinery) and untestable (which has no verdict to hang metadata off)."""
    from scripts import dump_robustness_fixtures as dumper

    result = getattr(dumper, builder_name)()

    assert set(result.keys()) == set(RESULT_KEYS)
    window = result["window"]
    assert window["bar_count"] > 0
    assert window["realized_start"] and window["realized_end"]
    assert window["realized_start"] <= window["realized_end"]


# --- TASK 2: coverage guard, refuse rather than clamp ------------------------


def test_truncated_tail_is_refused_and_names_both_windows(fake_download):
    # Asked through 2026; the vendor only has data to 2020.
    fake_download(_multiindex(_frame("2015-01-01", 1400)))

    with pytest.raises(InsufficientDataError) as exc:
        fetch_daily_bars("SPY", start="2015-01-01", end="2026-01-01")

    message = str(exc.value)
    assert "2026-01-01" in message, "must name what was REQUESTED"
    assert "2020" in message, "must name what was AVAILABLE"
    assert "SPY" in message


def test_truncated_head_is_refused_and_names_both_windows(fake_download):
    # Asked from 2010; the ticker did not exist until 2015. Not a bug -- but
    # not something to paper over either.
    fake_download(_multiindex(_frame("2015-01-02", 1400)))

    with pytest.raises(InsufficientDataError) as exc:
        fetch_daily_bars("SPY", start="2010-01-01", end=None)

    message = str(exc.value)
    assert "2010-01-01" in message
    assert "2015-01-02" in message


def test_a_start_landing_on_a_weekend_still_passes(fake_download):
    # 2015-01-03 was a Saturday; the first bar is Monday the 5th. Two days
    # short is inside tolerance and must not be an error.
    fake_download(_multiindex(_frame("2015-01-05", 400)))

    frame = fetch_daily_bars("SPY", start="2015-01-03", end=None)

    assert len(frame) == 400


def test_a_trailing_holiday_gap_still_passes(fake_download):
    frame = _frame("2015-01-01", 400)
    last = frame.index.max()
    fake_download(_multiindex(frame))

    # Ask for a few days past the last bar -- vendor lag, inside tolerance.
    requested_end = (last + pd.Timedelta(days=3)).date().isoformat()
    result = fetch_daily_bars("SPY", start="2015-01-01", end=requested_end)

    assert len(result) == 400


def test_coverage_tolerances_are_env_configurable(fake_download, monkeypatch):
    fake_download(_multiindex(_frame("2015-01-20", 400)))

    # 19 days short at the head: refused at the default tolerance of 7...
    with pytest.raises(InsufficientDataError):
        fetch_daily_bars("SPY", start="2015-01-01", end=None)

    # ...accepted once the tolerance is widened past the shortfall.
    monkeypatch.setenv("NLSB_COVERAGE_TOLERANCE_DAYS_START", "30")
    assert len(fetch_daily_bars("SPY", start="2015-01-01", end=None)) == 400


def test_there_is_no_silent_clamp_path(fake_download):
    """The whole point: a short frame either raises or is returned in full. It
    is never quietly returned as an answer to a narrower question."""
    fake_download(_multiindex(_frame("2015-01-01", 1400)))

    try:
        frame = fetch_daily_bars("SPY", start="2015-01-01", end="2026-01-01")
    except InsufficientDataError:
        return  # refused -- correct
    # If it did NOT raise, the frame must cover what was asked for; a
    # narrowed-but-successful return is the failure this test exists to catch.
    pytest.fail(f"short frame returned silently, {len(frame)} bars, no error")


# --- TASK 3: the effective-bar floor -----------------------------------------


def test_effective_bar_floor_is_where_the_statistics_stop_being_degenerate():
    """Not a round number. N bars give N-1 returns, and below 4 returns the
    deflated Sharpe's kurtosis term is a constant of the sample size rather
    than a property of the data."""
    assert MIN_EFFECTIVE_BARS == 5


def test_window_below_the_floor_is_rejected():
    ir = {
        "asset": {"ticker": "SPY", "asset_class": "equity"},
        "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}],
        "entry": {"left": "rsi14", "op": "<", "right": 30},
        "exit": {"left": "rsi14", "op": ">", "right": 70},
        "position": {"direction": "long", "size": "full"},
        "risk": None,
    }
    # RSI(14) warmup is 14 bars; 17 bars leaves 3 effective -- under the floor.
    with pytest.raises(Exception) as exc:
        service.confirm_robustness(ir, _frame("2015-01-01", 17), [])

    assert "warmup" in str(exc.value).lower()


def test_a_short_but_valid_window_still_reaches_untestable_not_an_error():
    """The floor raised here is 'meaningless', not 'uncertain'. A window too
    short for walk-forward's 756/252/252 has a designed answer already -- the
    UNTESTABLE verdict -- and must still get it."""
    from scripts import dump_robustness_fixtures as dumper

    result = dumper.build_untestable()

    assert result["kind"] == "full"
    assert result["verdict"]["verdict"] == "UNTESTABLE"
    assert result["window"]["bar_count"] > MIN_EFFECTIVE_BARS


# --- TASK 4: timeout, bounded retry, bounded cache ---------------------------


def test_fetch_passes_an_explicit_timeout(fake_download, monkeypatch):
    monkeypatch.setenv("NLSB_YFINANCE_TIMEOUT_SECONDS", "12.5")
    calls = fake_download(_multiindex(_frame("2015-01-01", 400)))

    fetch_daily_bars("SPY", start="2015-01-01")

    assert calls["kwargs"][0]["timeout"] == 12.5


def test_transport_failure_is_retried_a_bounded_number_of_times(fake_download, monkeypatch):
    monkeypatch.setenv("NLSB_YFINANCE_MAX_RETRIES", "2")
    monkeypatch.setattr(market_data.time, "sleep", lambda _s: None)  # no real backoff
    calls = fake_download(ConnectionError("simulated provider outage"))

    with pytest.raises(ConnectionError):
        fetch_daily_bars("SPY", start="2015-01-01")

    assert calls["n"] == 3, "2 retries after the first attempt, and no more"


def test_retries_are_configurable_down_to_none(fake_download, monkeypatch):
    monkeypatch.setenv("NLSB_YFINANCE_MAX_RETRIES", "0")
    monkeypatch.setattr(market_data.time, "sleep", lambda _s: None)
    calls = fake_download(ConnectionError("simulated provider outage"))

    with pytest.raises(ConnectionError):
        fetch_daily_bars("SPY", start="2015-01-01")

    assert calls["n"] == 1


def test_a_validation_failure_is_not_retried(fake_download, monkeypatch):
    """Retry the transport, never the verdict: re-asking for a frame that was
    too short just delays a 422 the caller can act on."""
    monkeypatch.setattr(market_data.time, "sleep", lambda _s: None)
    calls = fake_download(_multiindex(_frame("2015-01-01", 10)))  # under min_bars

    with pytest.raises(InsufficientDataError):
        fetch_daily_bars("SPY", start="2015-01-01")

    assert calls["n"] == 1


@pytest.fixture
def price_cache_on(monkeypatch):
    monkeypatch.setenv("NLSB_PRICE_CACHE_ENABLED", "true")
    price_cache.clear()
    yield
    price_cache.clear()


def test_identical_request_twice_makes_one_network_call(price_cache_on, fake_download):
    calls = fake_download(_multiindex(_frame("2015-01-01", 400)))

    first = fetch_daily_bars("SPY", start="2015-01-01", end=None)
    second = fetch_daily_bars("SPY", start="2015-01-01", end=None)

    assert calls["n"] == 1
    pd.testing.assert_frame_equal(first, second)


def test_cache_hit_reports_the_same_realized_window(price_cache_on, fake_download):
    fake_download(_multiindex(_frame("2015-01-01", 400)))

    fresh = realized_window(fetch_daily_bars("SPY", start="2015-01-01"), "2015-01-01", None)
    hit = realized_window(fetch_daily_bars("SPY", start="2015-01-01"), "2015-01-01", None)

    assert fresh == hit


def test_cache_returns_a_copy_not_the_shared_frame(price_cache_on, fake_download):
    fake_download(_multiindex(_frame("2015-01-01", 400)))

    first = fetch_daily_bars("SPY", start="2015-01-01")
    first.loc[first.index[0], "Close"] = -999.0
    second = fetch_daily_bars("SPY", start="2015-01-01")

    assert second.iloc[0]["Close"] != -999.0


def test_a_failed_fetch_is_never_cached(price_cache_on, fake_download, monkeypatch):
    monkeypatch.setattr(market_data.time, "sleep", lambda _s: None)
    calls = fake_download(_multiindex(_frame("2015-01-01", 10)))  # fails min_bars

    with pytest.raises(InsufficientDataError):
        fetch_daily_bars("SPY", start="2015-01-01")
    assert len(price_cache) == 0

    with pytest.raises(InsufficientDataError):
        fetch_daily_bars("SPY", start="2015-01-01")
    assert calls["n"] == 2, "a failure must not be served from cache"


def test_a_coverage_failure_is_never_cached(price_cache_on, fake_download):
    fake_download(_multiindex(_frame("2015-01-01", 1400)))

    with pytest.raises(InsufficientDataError):
        fetch_daily_bars("SPY", start="2015-01-01", end="2026-01-01")

    assert len(price_cache) == 0


def test_cache_key_separates_distinct_requests(price_cache_on, fake_download):
    calls = fake_download(_multiindex(_frame("2015-01-01", 400)))

    fetch_daily_bars("SPY", start="2015-01-01")
    fetch_daily_bars("QQQ", start="2015-01-01")  # different ticker
    fetch_daily_bars("SPY", start="2015-01-02")  # different start

    assert calls["n"] == 3


def test_cache_is_bounded_and_evicts_oldest(price_cache_on, fake_download, monkeypatch):
    """Bounded size is a security property: unbounded, anyone could exhaust
    memory with distinct ticker/date combinations."""
    monkeypatch.setenv("NLSB_PRICE_CACHE_SIZE", "2")
    calls = fake_download(_multiindex(_frame("2015-01-01", 400)))

    for ticker in ("AAA", "BBB", "CCC"):
        fetch_daily_bars(ticker, start="2015-01-01")

    assert len(price_cache) == 2
    assert calls["n"] == 3

    fetch_daily_bars("AAA", start="2015-01-01")  # evicted -> refetch
    assert calls["n"] == 4
    fetch_daily_bars("CCC", start="2015-01-01")  # still resident
    assert calls["n"] == 4


def test_cache_disabled_fetches_every_time(fake_download, monkeypatch):
    monkeypatch.setenv("NLSB_PRICE_CACHE_ENABLED", "false")
    price_cache.clear()
    calls = fake_download(_multiindex(_frame("2015-01-01", 400)))

    fetch_daily_bars("SPY", start="2015-01-01")
    fetch_daily_bars("SPY", start="2015-01-01")

    assert calls["n"] == 2
    assert len(price_cache) == 0


# --- Boundary invariants -----------------------------------------------------


def test_a_timeout_becomes_the_existing_502_not_a_raw_500(fake_download, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(market_data.time, "sleep", lambda _s: None)
    fake_download(TimeoutError("simulated read timeout"))
    # Use the REAL fetcher so the timeout travels the production path.
    main.app.dependency_overrides.pop(main.get_price_fetcher, None)

    resp = TestClient(main.app).post(
        "/confirm",
        json={
            "ir": {
                "asset": {"ticker": "SPY", "asset_class": "equity"},
                "indicators": [
                    {"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}
                ],
                "entry": {"left": "rsi14", "op": "<", "right": 30},
                "exit": {"left": "rsi14", "op": ">", "right": 70},
                "position": {"direction": "long", "size": "full"},
                "risk": None,
            },
            "assumptions": [],
            "ticker": "SPY",
            "start": "2015-01-01",
        },
    )

    assert resp.status_code == 502
    assert "simulated read timeout" not in resp.text
    assert "Traceback" not in resp.text
    assert isinstance(resp.json()["detail"], str)


def test_a_coverage_refusal_becomes_a_422_naming_both_windows(fake_download):
    from fastapi.testclient import TestClient

    fake_download(_multiindex(_frame("2015-01-01", 1400)))
    main.app.dependency_overrides.pop(main.get_price_fetcher, None)

    resp = TestClient(main.app).post(
        "/confirm",
        json={
            "ir": {
                "asset": {"ticker": "SPY", "asset_class": "equity"},
                "indicators": [
                    {"id": "rsi14", "type": "RSI", "params": {"period": 14}, "source": "close"}
                ],
                "entry": {"left": "rsi14", "op": "<", "right": 30},
                "exit": {"left": "rsi14", "op": ">", "right": 70},
                "position": {"direction": "long", "size": "full"},
                "risk": None,
            },
            "assumptions": [],
            "ticker": "SPY",
            "start": "2015-01-01",
            "end": "2026-01-01",
        },
    )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "2026-01-01" in detail and "2020" in detail
    assert "Traceback" not in resp.text
