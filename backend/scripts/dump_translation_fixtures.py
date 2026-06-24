"""Dump real `render_confirmation` output for the frontend's translation
contract tests, the same schema-true-fixture approach `dump_robustness_fixtures.py`
established in Phase 5a: never hand-author the text the frontend tests
against, since it would silently drift from `app.translation.renderer`'s
actual output. Both fixtures run `apply_defaults` + `render_confirmation`
directly -- no LLM call, no network -- and are dumped in exactly the shape
`main.TranslationPayload` serializes over HTTP.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from app.translation.defaults import apply_defaults
from app.translation.renderer import render_confirmation

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "fixtures" / "translation"


def _payload(sparse_ir: dict) -> dict:
    full_ir, assumptions = apply_defaults(sparse_ir)
    restatement = render_confirmation(full_ir, assumptions)
    return {
        "status": "ok",
        "ir": full_ir,
        "assumptions": [dataclasses.asdict(a) for a in assumptions],
        "restatement": restatement,
        "message": None,
        "retries": 0,
    }


def build_ordinary_assumptions() -> dict:
    """Exit IS stated -- only routine note-severity assumptions (period,
    source, position sizing, risk). No SEVERITY_WARNING anywhere."""
    return _payload(
        {
            "asset": {"ticker": "SPY"},
            "indicators": [{"id": "rsi14", "type": "RSI"}],
            "entry": {"left": "rsi14", "op": "<", "right": 30},
            "exit": {"left": "rsi14", "op": ">", "right": 70},
        }
    )


def build_no_exit_warning() -> dict:
    """No exit stated -- the SEVERITY_WARNING case: defaulting silently
    turns this into buy-and-hold-from-first-entry."""
    return _payload(
        {
            "asset": {"ticker": "SPY"},
            "indicators": [{"id": "rsi14", "type": "RSI", "params": {"period": 14}}],
            "entry": {"left": "rsi14", "op": "<", "right": 30},
        }
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "ordinary_assumptions.json": build_ordinary_assumptions(),
        "no_exit_warning.json": build_no_exit_warning(),
    }
    for name, payload in fixtures.items():
        path = OUT_DIR / name
        path.write_text(json.dumps(payload, indent=2, allow_nan=False))
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
