"""Pins `scripts/dump_translation_fixtures.py`'s output against the real
defaulting/renderer code, exactly the way `test_robustness_fixtures.py`
pins the robustness fixtures in Phase 5a -- so a future change to
`defaults.py`/`renderer.py` that silently changes the dumped JSON fails a
backend test, not just "the frontend tests started looking weird."
"""

from __future__ import annotations

from scripts.dump_translation_fixtures import build_no_exit_warning, build_ordinary_assumptions


def test_ordinary_assumptions_fixture_has_no_warning_severity_assumption():
    payload = build_ordinary_assumptions()
    assert payload["status"] == "ok"
    assert all(a["severity"] == "note" for a in payload["assumptions"])
    assert "Heads up" not in payload["restatement"]


def test_no_exit_warning_fixture_carries_the_severity_warning_assumption():
    payload = build_no_exit_warning()
    assert payload["status"] == "ok"
    warnings = [a for a in payload["assumptions"] if a["severity"] == "warning"]
    assert len(warnings) == 1
    assert warnings[0]["field"] == "exit"
    assert "buy-and-hold" in warnings[0]["reason"]
    assert "Heads up" in payload["restatement"]
