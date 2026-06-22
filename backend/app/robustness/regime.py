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
    labels = _regime_labels(price_data["Close"]).reindex(eff_index)

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

    return RegimeReport(
        breakdowns=tuple(breakdowns),
        concentrated_regime=concentrated_regime,
        concentration_share=concentration_share,
    )


def _regime_labels(close: pd.Series) -> pd.Series:
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

    combined = trend.astype(str) + "_" + vol_label.astype(str)
    combined[trend.isna() | vol_label.isna()] = None
    return combined


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
