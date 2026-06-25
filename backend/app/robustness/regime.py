"""Regime segmentation and per-regime performance attribution.

Two independent, documented regime axes, combined into up to four labels
(e.g. "bull_high_vol"):
  - Trend: "bull" if Close > its 200-day SMA, else "bear". (Trailing-MA
    sign, not trailing-return sign -- chosen because the engine already has
    a tested SMA implementation; either is a defensible, simple rule.)
  - Volatility: 60-day trailing realized volatility (rolling std of daily
    simple returns) above or below the SAMPLE MEDIAN of that rolling series
    -> "high_vol" / "low_vol".

IMPORTANT -- this is full-sample, descriptive labeling, not a tradeable
signal: the volatility regime boundary is the median of the ENTIRE
trailing-vol series, computed with hindsight over the whole backtest
window. A strategy could not have known "vol is currently above the
eventual sample median" in real time. Regime breakdown answers "did this
strategy's results come from everywhere, or from one slice of history?" --
it is not a third trading rule and must never be fed back into the IR or
treated as something the strategy itself reacted to.

Concentration is checked two ways: per 2x2 cell (`concentrated_regime`) and
on the trend axis alone, MARGINALLY (`marginal_flags`) -- bull vs bear,
ignoring volatility entirely. The marginal check exists because a strategy
can split its gains ~50/50 across two cells that share a trend (e.g.
bull_high_vol and bull_low_vol) and never trip the 80% cell threshold in
either, while still owning ~100% of its gains from "bull markets" --
exactly the "only worked in the 2020-21 bull run" story (2020 =
bull/high-vol crash-recover, 2021 = bull/low-vol grind up).

The marginal check is BENCHMARK-RELATIVE, not absolute: an unconditional
80%-of-gains-in-bull-regimes threshold flags nearly every long-only
strategy, including plain buy-and-hold, because the market itself parks
most of its own gains in bull regimes (by this module's own bull/bear
definition). What's actually informative is whether a strategy is MORE
bull-concentrated than the asset it trades -- i.e. whether the strategy
adds bull-dependence on top of the base rate the market already has.
`marginal_flags` therefore reports a strategy's bull-regime gains share
MINUS a same-window buy-and-hold benchmark's bull-regime gains share
(`excess`), and only flags when that excess clears a threshold. Buy-and-
hold itself nets out to ~zero excess against its own benchmark and never
flags, by construction.

Every return figure here comes from `run_ir_backtest_returns`, which shares
100% of its computation with `run_ir_backtest` (same vectorbt portfolio,
same cost model) -- this module only re-buckets the per-bar returns that
call already produced; it never re-simulates the strategy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from app.engine.backtest import TRADING_DAYS_PER_YEAR, run_ir_backtest_returns

MA_PERIOD = 200
VOL_WINDOW = 60

# A single regime accounting for this share (or more) of the strategy's
# total POSITIVE per-bar returns (gains only, losses excluded) is flagged
# as concentrated. Heuristic (documented, not from literature): catches
# "it only worked in the 2020-21 bull run" without requiring a precise
# statistical test. Using gains-only keeps the share bounded in [0, 1]
# regardless of how losses are distributed across regimes.
CONCENTRATION_SHARE_THRESHOLD = 0.8

# How much MORE of its gains-only share a strategy can own in bull regimes
# than a same-window buy-and-hold benchmark does, before that excess is
# flagged at all. Not from literature -- chosen as a deliberately wide band
# so estimation noise in a benchmark computed from the same finite price
# series doesn't trip the flag on a strategy that is, in substance, no more
# bull-dependent than the market it trades.
MARGINAL_BULL_EXCESS_THRESHOLD = 0.15

# Excess above this (threshold + 0.05) is reported with confidence
# "confirmed" rather than "provisional". The 0.05 band is an honest
# acknowledgment that `excess` is the difference of two noisy share
# estimates -- a strategy landing just past the bare threshold could be
# benchmark-level dependence plus noise, not a real signal.
MARGINAL_BULL_EXCESS_CONFIRMED_THRESHOLD = 0.20


@dataclass(frozen=True)
class RegimeBreakdown:
    regime: str
    share_of_time: float
    total_return: float
    sharpe_ratio: float
    num_entries: int
    num_bars: int


@dataclass(frozen=True)
class RegimeReport:
    breakdowns: tuple
    concentrated_regime: str | None
    concentration_share: float | None
    # Each element is a plain dict (not a dataclass) -- this is the
    # JSON-serializable shape `run_robustness` returns directly, with no
    # `dataclasses.asdict` conversion step needed for this field. See
    # `_detect_bull_concentration` for the schema.
    marginal_flags: tuple = ()


def run_regime_analysis(
    ir: dict,
    price_data: pd.DataFrame,
    *,
    fees: float = 0.0,
    slippage: float = 0.0005,
) -> RegimeReport:
    daily_returns, eff_entries = run_ir_backtest_returns(ir, price_data, fees=fees, slippage=slippage)
    eff_index = daily_returns.index

    close = price_data["Close"].reindex(eff_index)
    trend_labels, vol_labels = _axis_labels(price_data["Close"])
    trend_labels = trend_labels.reindex(eff_index)
    vol_labels = vol_labels.reindex(eff_index)
    labels = _combine_labels(trend_labels, vol_labels)

    valid = labels.notna()
    total_bars = int(valid.sum())

    breakdowns = []
    for regime in sorted(labels.dropna().unique()):
        mask = valid & (labels == regime)
        num_bars = int(mask.sum())
        regime_returns = daily_returns[mask]
        total_return = float((1 + regime_returns).prod() - 1) if num_bars > 0 else float("nan")
        std = regime_returns.std()
        sharpe = (
            float(regime_returns.mean() / std * math.sqrt(TRADING_DAYS_PER_YEAR))
            if std and std > 0
            else float("nan")
        )
        num_entries = int(eff_entries[mask].sum())
        breakdowns.append(
            RegimeBreakdown(
                regime=regime,
                share_of_time=num_bars / total_bars if total_bars > 0 else float("nan"),
                total_return=total_return,
                sharpe_ratio=sharpe,
                num_entries=num_entries,
                num_bars=num_bars,
            )
        )

    concentrated_regime, concentration_share = _detect_concentration(breakdowns, daily_returns, valid, labels)

    # Computed from the full (untrimmed) Close series, THEN reindexed to
    # eff_index -- not from the already-trimmed `close` above -- so the
    # first eff-window bar gets its real day-over-day return instead of a
    # spurious NaN from having no predecessor left in a pre-trimmed series.
    benchmark_returns = price_data["Close"].pct_change().reindex(eff_index)
    marginal_flags = _detect_bull_concentration(daily_returns, benchmark_returns, valid, trend_labels)

    return RegimeReport(
        breakdowns=tuple(breakdowns),
        concentrated_regime=concentrated_regime,
        concentration_share=concentration_share,
        marginal_flags=marginal_flags,
    )


def _axis_labels(close: pd.Series) -> tuple:
    """The two regime axes, computed independently of each other and of
    the combined cell label -- the marginal concentration check needs each
    axis on its own, not parsed back out of the combined string."""
    ma200 = close.rolling(MA_PERIOD).mean()
    trend = pd.Series(index=close.index, dtype=object)
    trend[close > ma200] = "bull"
    trend[close <= ma200] = "bear"
    trend[ma200.isna()] = None

    daily_simple_returns = close.pct_change()
    trailing_vol = daily_simple_returns.rolling(VOL_WINDOW).std()
    vol_median = trailing_vol.median()
    vol_label = pd.Series(index=close.index, dtype=object)
    vol_label[trailing_vol > vol_median] = "high_vol"
    vol_label[trailing_vol <= vol_median] = "low_vol"
    vol_label[trailing_vol.isna()] = None

    return trend, vol_label


def _combine_labels(trend: pd.Series, vol_label: pd.Series) -> pd.Series:
    combined = trend.astype(str) + "_" + vol_label.astype(str)
    combined[trend.isna() | vol_label.isna()] = None
    return combined


def _regime_labels(close: pd.Series) -> pd.Series:
    trend, vol_label = _axis_labels(close)
    return _combine_labels(trend, vol_label)


def _detect_concentration(
    breakdowns: list[RegimeBreakdown],
    daily_returns: pd.Series,
    valid: pd.Series,
    labels: pd.Series,
) -> tuple:
    positive_returns = daily_returns.clip(lower=0)
    total_positive = positive_returns[valid].sum()
    if not total_positive or total_positive <= 0:
        return None, None

    best_regime = None
    best_share = 0.0
    for b in breakdowns:
        mask = valid & (labels == b.regime)
        share = positive_returns[mask].sum() / total_positive
        if share > best_share:
            best_share = share
            best_regime = b.regime

    if best_share >= CONCENTRATION_SHARE_THRESHOLD:
        return best_regime, float(best_share)
    return None, None


def _detect_bull_concentration(
    daily_returns: pd.Series,
    benchmark_returns: pd.Series,
    valid: pd.Series,
    trend_labels: pd.Series,
) -> tuple:
    """Benchmark-relative version of the trend-axis marginal check: how
    much MORE of its gains-only share does the strategy own in bull-labeled
    bars than a same-window buy-and-hold benchmark does, using the SAME
    bull/bear labels for both (so the comparison isn't confounded by a
    different regime definition). `benchmark_returns` must already be
    aligned to `daily_returns`'s index by the caller -- this function does
    not resolve a mismatched benchmark series, it only consumes one.

    Returns an empty tuple if either the strategy or the benchmark has no
    positive return at all over the valid window (gains-only share is
    undefined in that case, not zero) -- a strategy can't be said to be
    MORE bull-concentrated than a benchmark whose own share can't be
    computed."""
    positive_returns = daily_returns.clip(lower=0)
    total_positive = positive_returns[valid].sum()
    if not total_positive or total_positive <= 0:
        return ()

    benchmark_positive = benchmark_returns.clip(lower=0)
    benchmark_total_positive = benchmark_positive[valid].sum()
    if not benchmark_total_positive or benchmark_total_positive <= 0:
        return ()

    bull_mask = valid & (trend_labels == "bull")
    strategy_bull_share = float(positive_returns[bull_mask].sum() / total_positive)
    benchmark_bull_share = float(benchmark_positive[bull_mask].sum() / benchmark_total_positive)
    excess = strategy_bull_share - benchmark_bull_share

    if excess <= MARGINAL_BULL_EXCESS_THRESHOLD:
        return ()

    confidence = "confirmed" if excess > MARGINAL_BULL_EXCESS_CONFIRMED_THRESHOLD else "provisional"
    return (
        {
            "flag": "bull_concentration",
            "confidence": confidence,
            "excess": round(excess, 4),
            "strategy_bull_share": round(strategy_bull_share, 4),
            "benchmark_bull_share": round(benchmark_bull_share, 4),
        },
    )
