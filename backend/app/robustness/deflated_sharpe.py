"""Probabilistic Sharpe Ratio (PSR) and Deflated Sharpe Ratio (DSR).

Source:
  Bailey, D.H. and M. Lopez de Prado (2012), "The Sharpe Ratio Efficient
  Frontier", Journal of Risk. (PSR formula; SSRN 1821643 / slide deck
  "The Sharp Razor", SSRN 2150879.)
  Bailey, D.H. and M. Lopez de Prado (2014), "The Deflated Sharpe Ratio:
  Correcting for Selection Bias, Backtest Overfitting, and Non-Normality",
  Journal of Portfolio Management. (DSR / multiple-testing threshold SR0;
  SSRN 2460551.)

  PSR(SR*) = Z[ (SR_hat - SR*) * sqrt(n-1) / sqrt(1 - skew*SR_hat + ((kurt-1)/4)*SR_hat^2) ]
  DSR = PSR(SR0), where SR0 = sqrt(Var(SR_trials)) *
        [ (1-g)*Z^-1(1 - 1/N) + g*Z^-1(1 - 1/(N*e)) ],  g = Euler-Mascheroni.

VERIFICATION (pinned in tests, not just asserted): Bailey & Lopez de Prado's
own slide deck ("The Sharp Razor", SSRN 2150879, pp. 16-17) gives a fully
worked example -- a 2-year monthly track record with mean=0.036, stdev=0.079,
skew=-2.448, kurtosis=10.164 (non-excess), per-period SR=0.458 (n=24) -- and
states PSR(0) = 0.913 for that fund, and PSR(0) = 0.982 for a fund with the
SAME per-period Sharpe ratio but Gaussian returns (skew=0, kurtosis=3).
Plugging those exact numbers into the formula above by hand reproduces both
0.913 and 0.982. `test_deflated_sharpe.py` pins this.

TWO TRAPS THAT WILL SILENTLY CORRUPT THE RESULT:

1. PER-PERIOD, NOT ANNUALIZED, SHARPE. The skew/kurtosis correction and the
   sqrt(n-1) scaling are derived for the per-observation (non-annualized) SR.
   Plugging in the annualized SR for the same example above (1.585 instead
   of 0.458) gives PSR(0) ~= 0.99, not 0.913 -- a different, wrong answer
   that LOOKS plausible (it's still a probability in [0,1]). This module's
   public functions take per-period returns/Sharpe; callers must not pass
   annualized figures. `test_annualized_sharpe_in_place_of_per_period_gives_wrong_psr`
   demonstrates the corruption directly.

2. NON-EXCESS KURTOSIS. The formula's `kurt` is the regular (Pearson) fourth
   moment ratio, where a Gaussian has kurt=3 -- NOT "excess kurtosis"
   (Gaussian=0), which is what `scipy.stats.kurtosis()` returns by default
   (`fisher=True`). This module always calls `scipy.stats.kurtosis(...,
   fisher=False)`. `test_kurtosis_convention_is_non_excess_gaussian_equals_three`
   pins the convention directly against a large Gaussian sample.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.stats import kurtosis as _scipy_kurtosis
from scipy.stats import norm
from scipy.stats import skew as _scipy_skew

EULER_MASCHERONI = 0.5772156649015329


def estimated_sharpe_ratio(returns: Sequence[float]) -> float:
    """Per-period Sharpe ratio: mean / sample std (ddof=1), risk-free rate = 0."""
    arr = np.asarray(returns, dtype=float)
    std = arr.std(ddof=1)
    if std == 0:
        return float("nan")
    return float(arr.mean() / std)


def sample_skew(returns: Sequence[float]) -> float:
    return float(_scipy_skew(np.asarray(returns, dtype=float)))


def sample_kurtosis(returns: Sequence[float]) -> float:
    """Non-excess kurtosis (Gaussian = 3) -- ``fisher=False`` is required;
    the PSR formula's ``(kurt - 1)/4`` term assumes this convention."""
    return float(_scipy_kurtosis(np.asarray(returns, dtype=float), fisher=False))


def psr_from_stats(
    sr_hat: float, n: int, skew: float, kurtosis: float, sr_benchmark: float = 0.0
) -> float:
    """PSR(sr_benchmark) from precomputed per-period stats (no raw returns needed).

    ``sr_hat`` and ``sr_benchmark`` must both be PER-PERIOD Sharpe ratios.
    ``kurtosis`` must be NON-EXCESS (Gaussian = 3).
    """
    if n < 2:
        raise ValueError("psr_from_stats requires at least 2 observations")
    numerator = (sr_hat - sr_benchmark) * math.sqrt(n - 1)
    denom_sq = 1 - skew * sr_hat + ((kurtosis - 1) / 4) * sr_hat**2
    if denom_sq <= 0:
        raise ValueError(
            f"PSR denominator is non-positive ({denom_sq!r}) for this "
            "skew/kurtosis/SR combination -- inputs are degenerate"
        )
    return float(norm.cdf(numerator / math.sqrt(denom_sq)))


def probabilistic_sharpe_ratio(returns: Sequence[float], sr_benchmark: float = 0.0) -> float:
    """PSR(sr_benchmark) computed directly from a per-period returns series."""
    arr = np.asarray(returns, dtype=float)
    sr_hat = estimated_sharpe_ratio(arr)
    return psr_from_stats(
        sr_hat,
        n=len(arr),
        skew=sample_skew(arr),
        kurtosis=sample_kurtosis(arr),
        sr_benchmark=sr_benchmark,
    )


def trial_sharpe_variance(trial_sharpes: Sequence[float]) -> float:
    """Cross-sectional variance of per-period Sharpe ratios across N trials."""
    arr = np.asarray(trial_sharpes, dtype=float)
    if len(arr) < 2:
        return 0.0
    return float(arr.var(ddof=1))


def sr0_threshold(var_sr_trials: float, n_trials: int) -> float:
    """Multiple-testing-adjusted Sharpe threshold SR0 (the expected maximum
    Sharpe ratio one would see across ``n_trials`` configurations under the
    null of no skill -- the bar a real strategy's Sharpe must clear).

    Assumes the trial Sharpes are centered at zero under that null; only
    their variance enters, not their mean (matching the formula as given:
    no mean-of-trials term).
    """
    if n_trials < 2:
        raise ValueError("sr0_threshold requires at least 2 trials")
    if var_sr_trials < 0:
        raise ValueError("var_sr_trials must be non-negative")
    z1 = norm.ppf(1 - 1 / n_trials)
    z2 = norm.ppf(1 - 1 / (n_trials * math.e))
    max_z = (1 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2
    return math.sqrt(var_sr_trials) * max_z


def deflated_sharpe_ratio(returns: Sequence[float], var_sr_trials: float, n_trials: int) -> float:
    """DSR = PSR(SR0): the strategy's per-period returns evaluated against
    the multiple-testing-adjusted threshold rather than against zero."""
    sr0 = sr0_threshold(var_sr_trials, n_trials)
    return probabilistic_sharpe_ratio(returns, sr_benchmark=sr0)


def deflated_sharpe_ratio_from_trials(returns: Sequence[float], trial_sharpes: Sequence[float]) -> dict:
    """DSR computed with N and Var(SR_trials) sourced from the ACTUAL list of
    per-period Sharpe ratios the search evaluated (e.g. every grid point
    `sensitivity.run_sensitivity` ran) -- more configs tried means a higher
    bar, which is the whole point of the multiple-testing correction.

    Returns a dict with the intermediate values so callers/tests can see
    exactly what fed into the deflation, not just the final number.
    """
    n_trials = len(trial_sharpes)
    if n_trials < 2:
        return {
            "n_trials": n_trials,
            "var_sr_trials": 0.0,
            "sr0": 0.0,
            "dsr": probabilistic_sharpe_ratio(returns, sr_benchmark=0.0),
        }
    var_sr = trial_sharpe_variance(trial_sharpes)
    sr0 = sr0_threshold(var_sr, n_trials)
    dsr = probabilistic_sharpe_ratio(returns, sr_benchmark=sr0)
    return {"n_trials": n_trials, "var_sr_trials": var_sr, "sr0": sr0, "dsr": dsr}
