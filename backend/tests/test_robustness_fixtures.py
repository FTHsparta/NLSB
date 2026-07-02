"""Pins `scripts.dump_robustness_fixtures`'s builders to the verdict state
each is supposed to demonstrate. If a future change to `verdict.py`'s
thresholds shifts one of these canned inputs into a different bucket, this
test fails loudly -- the frontend fixture JSON committed in
`frontend/fixtures/robustness/` would otherwise silently go stale (a
"PASS" fixture the renderer test suite checks against `verdict.py` no
longer actually classifying as PASS) until someone happened to look.
Re-run `python -m scripts.dump_robustness_fixtures` after any verdict.py
threshold change and re-commit the regenerated JSON alongside it.
"""

from app.robustness.regime import MARGINAL_BULL_EXCESS_CONFIRMED_THRESHOLD, MARGINAL_BULL_EXCESS_THRESHOLD
from scripts.dump_robustness_fixtures import (
    build_bull_concentration_confirmed,
    build_bull_concentration_provisional,
    build_bull_concentration_with_verdict,
    build_likely_overfit,
    build_no_exit,
    build_pass,
    build_shaky,
    build_untestable,
)


def test_build_pass_is_actually_pass():
    assert build_pass()["verdict"]["verdict"] == "PASS"


def test_build_shaky_is_actually_shaky():
    assert build_shaky()["verdict"]["verdict"] == "SHAKY"


def test_build_likely_overfit_is_actually_likely_overfit():
    assert build_likely_overfit()["verdict"]["verdict"] == "LIKELY_OVERFIT"


def test_build_untestable_is_actually_untestable():
    assert build_untestable()["verdict"]["verdict"] == "UNTESTABLE"


def test_build_no_exit_is_actually_no_exit_with_a_real_first_entry():
    result = build_no_exit()
    assert result["kind"] == "no_exit"
    assert result["verdict"] is None
    assert result["no_exit"]["first_entry_date"] is not None


def test_build_bull_concentration_confirmed_actually_fires_confirmed():
    """Pins the Phase 4d.1 fixture this whole render path depends on:
    if a future change to `regime.py`'s thresholds or the underlying
    series construction lets this scenario's excess fall back into the
    provisional band or below the flag threshold entirely, the frontend's
    "confirmed" render contract test would otherwise be exercising a
    fixture that no longer demonstrates "confirmed" at all."""
    result = build_bull_concentration_confirmed()
    flags = result["regime"]["marginal_flags"]
    assert len(flags) == 1
    assert flags[0]["flag"] == "bull_concentration"
    assert flags[0]["confidence"] == "confirmed"
    assert flags[0]["excess"] > MARGINAL_BULL_EXCESS_CONFIRMED_THRESHOLD


def test_build_bull_concentration_provisional_actually_fires_provisional():
    """Same rationale as the confirmed pin above, for the narrower
    provisional band -- this fixture's (seed, bear_noise) pair was found
    by direct search specifically because it lands in this band; pinning
    it here means a threshold change that closes the band, or a future
    edit to the series construction, fails the backend suite instead of
    silently leaving the frontend's "provisional" contract test exercising
    a fixture that's actually confirmed (or doesn't fire at all)."""
    result = build_bull_concentration_provisional()
    flags = result["regime"]["marginal_flags"]
    assert len(flags) == 1
    assert flags[0]["flag"] == "bull_concentration"
    assert flags[0]["confidence"] == "provisional"
    assert MARGINAL_BULL_EXCESS_THRESHOLD < flags[0]["excess"] <= MARGINAL_BULL_EXCESS_CONFIRMED_THRESHOLD


def test_build_bull_concentration_with_verdict_pairs_a_real_verdict_with_a_confirmed_flag():
    """Phase 9 fixture pin: this is the ONLY fixture pairing a non-UNTESTABLE
    verdict with a populated bull-concentration flag (the two other
    bull_concentration_* fixtures both land UNTESTABLE). It exists so the
    frontend can pin "flag renders alongside a real verdict card." If a
    threshold or series-construction change either demotes the verdict to
    UNTESTABLE or drops the flag below the confirmed band, this fails loudly
    rather than letting that frontend contract test go vacuous."""
    result = build_bull_concentration_with_verdict()
    assert result["kind"] == "full"
    assert result["verdict"]["verdict"] != "UNTESTABLE"
    flags = result["regime"]["marginal_flags"]
    assert len(flags) == 1
    assert flags[0]["flag"] == "bull_concentration"
    assert flags[0]["confidence"] == "confirmed"
    assert flags[0]["excess"] > MARGINAL_BULL_EXCESS_CONFIRMED_THRESHOLD
    # And it is genuinely testable, not untestable-in-disguise: real OOS
    # trades in every walk-forward fold are what keep it out of UNTESTABLE.
    assert all(fold["oos_num_trades"] > 0 for fold in result["walk_forward"]["folds"])
