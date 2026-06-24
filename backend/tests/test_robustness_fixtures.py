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

from scripts.dump_robustness_fixtures import (
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
