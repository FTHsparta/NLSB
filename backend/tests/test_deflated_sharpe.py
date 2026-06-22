"""Pins PSR/DSR against a published worked example, and guards the two
formula traps named in app/robustness/deflated_sharpe.py's docstring.

Reference: Bailey & Lopez de Prado, "The Sharp Razor: Deflating the Sharpe
Ratio by asking for a Minimum Track Record Length" (SSRN 2150879), pp.16-17.
A 2-year monthly track record: mean=0.036, stdev=0.079, skew=-2.448,
kurtosis=10.164 (non-excess), per-period SR=0.458 (n=24 monthly obs).
The slides state PSR(0)=0.913 for that (non-normal) fund, and PSR(0)=0.982
for a fund with the SAME per-period Sharpe but Gaussian returns (skew=0,
kurtosis=3). Both were hand-verified against the formula before writing
these assertions.
"""

import math

import numpy as np
import pytest
from scipy.stats import norm

from app.robustness.deflated_sharpe import (
    EULER_MASCHERONI,
    deflated_sharpe_ratio_from_trials,
    probabilistic_sharpe_ratio,
    psr_from_stats,
    sample_kurtosis,
    sample_skew,
    sr0_threshold,
    trial_sharpe_variance,
)

# The published example's stats.
_SR_HAT = 0.458
_N = 24
_SKEW_NON_NORMAL = -2.448
_KURT_NON_NORMAL = 10.164  # non-excess; Gaussian = 3
_ANNUALIZED_SR = 1.585  # sqrt(12) * 0.458, also given on the same slide


def test_psr_matches_published_non_normal_fund_example():
    psr = psr_from_stats(_SR_HAT, _N, _SKEW_NON_NORMAL, _KURT_NON_NORMAL, sr_benchmark=0.0)
    assert psr == pytest.approx(0.913, abs=0.002)


def test_psr_matches_published_normal_equivalent_fund_example():
    # Same per-period SR and n, but Gaussian returns: skew=0, kurtosis=3.
    psr = psr_from_stats(_SR_HAT, _N, skew=0.0, kurtosis=3.0, sr_benchmark=0.0)
    assert psr == pytest.approx(0.982, abs=0.002)


def test_trap_1_using_annualized_sharpe_corrupts_psr():
    """Per-period SR=0.458 gives PSR(0)=0.913. Mistakenly plugging in the
    annualized SR=1.585 for the same fund gives a materially different,
    wrong answer -- proving this trap actually corrupts the result rather
    than being a no-op."""
    correct_psr = psr_from_stats(_SR_HAT, _N, _SKEW_NON_NORMAL, _KURT_NON_NORMAL, 0.0)
    wrong_psr = psr_from_stats(_ANNUALIZED_SR, _N, _SKEW_NON_NORMAL, _KURT_NON_NORMAL, 0.0)
    assert correct_psr == pytest.approx(0.913, abs=0.002)
    assert abs(wrong_psr - correct_psr) > 0.05


def test_trap_2_excess_kurtosis_mislabeled_as_non_excess_corrupts_psr():
    """If excess kurtosis (Gaussian=0) is computed but fed into a formula
    that expects non-excess (Gaussian=3), the result is wrong. Excess
    kurtosis for this fund is 10.164 - 3 = 7.164."""
    correct_psr = psr_from_stats(_SR_HAT, _N, _SKEW_NON_NORMAL, _KURT_NON_NORMAL, 0.0)
    excess_kurt = _KURT_NON_NORMAL - 3
    wrong_psr = psr_from_stats(_SR_HAT, _N, _SKEW_NON_NORMAL, excess_kurt, 0.0)
    assert correct_psr == pytest.approx(0.913, abs=0.002)
    assert abs(wrong_psr - correct_psr) > 0.005


def test_sample_kurtosis_convention_is_non_excess_gaussian_equals_three():
    """scipy.stats.kurtosis defaults to EXCESS kurtosis (Gaussian=0).
    sample_kurtosis must override that (fisher=False) so a large Gaussian
    sample reads ~3, not ~0."""
    rng = np.random.default_rng(42)
    gaussian_sample = rng.normal(loc=0.001, scale=0.02, size=200_000)
    kurt = sample_kurtosis(gaussian_sample)
    assert kurt == pytest.approx(3.0, abs=0.05)


def test_sample_skew_zero_for_symmetric_gaussian():
    rng = np.random.default_rng(7)
    gaussian_sample = rng.normal(loc=0.0, scale=0.01, size=200_000)
    assert sample_skew(gaussian_sample) == pytest.approx(0.0, abs=0.02)


def test_probabilistic_sharpe_ratio_from_raw_returns_matches_stats_path():
    """psr_from_stats and probabilistic_sharpe_ratio(returns) must agree
    when fed returns whose sample stats equal the precomputed ones."""
    rng = np.random.default_rng(123)
    returns = rng.normal(loc=0.01, scale=0.05, size=500)
    sr_hat = returns.mean() / returns.std(ddof=1)
    skew = sample_skew(returns)
    kurt = sample_kurtosis(returns)
    from_stats = psr_from_stats(sr_hat, len(returns), skew, kurt, sr_benchmark=0.0)
    from_returns = probabilistic_sharpe_ratio(returns, sr_benchmark=0.0)
    assert from_returns == pytest.approx(from_stats, rel=1e-9)


def test_sr0_threshold_matches_independent_hand_computation():
    """Independently recompute SR0 via plain norm.ppf calls (not reusing
    sr0_threshold's internals) to check the wiring, not just re-assert it."""
    var_sr_trials = 0.01
    n_trials = 100
    z1 = norm.ppf(1 - 1 / 100)
    z2 = norm.ppf(1 - 1 / (100 * math.e))
    expected = math.sqrt(0.01) * ((1 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2)
    assert sr0_threshold(var_sr_trials, n_trials) == pytest.approx(expected, rel=1e-9)


def test_sr0_threshold_increases_with_more_trials():
    """More configurations tried -> higher bar to clear -- the core point
    of the multiple-testing correction."""
    sr0_10 = sr0_threshold(0.01, 10)
    sr0_100 = sr0_threshold(0.01, 100)
    sr0_1000 = sr0_threshold(0.01, 1000)
    assert sr0_10 < sr0_100 < sr0_1000


def test_sr0_threshold_increases_with_trial_variance():
    sr0_low_var = sr0_threshold(0.001, 50)
    sr0_high_var = sr0_threshold(0.05, 50)
    assert sr0_low_var < sr0_high_var


def test_trial_sharpe_variance_matches_numpy_sample_variance():
    trials = [0.1, 0.3, -0.2, 0.5, 0.0, 0.25]
    assert trial_sharpe_variance(trials) == pytest.approx(np.var(trials, ddof=1))


def test_deflated_sharpe_ratio_from_trials_sources_n_from_trial_list_length():
    rng = np.random.default_rng(99)
    returns = rng.normal(loc=0.02, scale=0.04, size=300)
    few_trials = [0.05, -0.03, 0.02]
    many_trials = list(rng.normal(loc=0.0, scale=0.1, size=500))

    few = deflated_sharpe_ratio_from_trials(returns, few_trials)
    many = deflated_sharpe_ratio_from_trials(returns, many_trials)

    assert few["n_trials"] == 3
    assert many["n_trials"] == 500
    # more trials evaluated -> higher (or equal) deflation threshold, given
    # comparable trial variance -- check the threshold tracks N directly.
    same_var_trials_more_n = list(few_trials) * 50  # same variance, 50x the N
    same_var_result = deflated_sharpe_ratio_from_trials(returns, same_var_trials_more_n)
    assert same_var_result["sr0"] > few["sr0"]


def test_deflated_sharpe_ratio_from_trials_with_few_trials_falls_back_to_psr_zero():
    rng = np.random.default_rng(5)
    returns = rng.normal(loc=0.01, scale=0.03, size=200)
    result = deflated_sharpe_ratio_from_trials(returns, [0.1])
    assert result["n_trials"] == 1
    assert result["sr0"] == 0.0
    assert result["dsr"] == pytest.approx(probabilistic_sharpe_ratio(returns, 0.0))


def test_psr_raises_on_degenerate_denominator():
    # 1 - skew*sr + ((kurt-1)/4)*sr^2 = 1 - 20*10 + 0 = -199 < 0.
    with pytest.raises(ValueError):
        psr_from_stats(sr_hat=10.0, n=30, skew=20.0, kurtosis=1.0, sr_benchmark=0.0)


def test_sr0_threshold_requires_at_least_two_trials():
    with pytest.raises(ValueError):
        sr0_threshold(0.01, 1)
