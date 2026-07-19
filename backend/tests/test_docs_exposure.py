"""NLSB_ENV=production must remove the auto-docs surface entirely: /docs,
/redoc, AND /openapi.json (the last one is the machine-readable schema --
leaving it up hands out the full API description even with both UIs off).
Real routes are unaffected in both modes.

The app is constructed at import time, so unlike the dependency-override
tests these must rebuild the module under a controlled env via
importlib.reload; teardown reloads once more with NLSB_ENV cleared so the
module-global `app` other test files import stays the dev-mode one.
"""

from __future__ import annotations

import importlib
import os

import pytest
from fastapi.testclient import TestClient

import app.main as main_module


@pytest.fixture
def build_app(monkeypatch):
    def _build(env: str | None):
        if env is None:
            monkeypatch.delenv("NLSB_ENV", raising=False)
        else:
            monkeypatch.setenv("NLSB_ENV", env)
        return importlib.reload(main_module).app

    yield _build

    # monkeypatch's own undo runs after this fixture's teardown, so clear the
    # env by hand before the restoring reload.
    os.environ.pop("NLSB_ENV", None)
    importlib.reload(main_module)


def test_production_disables_docs_but_not_routes(build_app) -> None:
    client = TestClient(build_app("production"))
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/health").status_code == 200


def test_dev_default_keeps_docs(build_app) -> None:
    client = TestClient(build_app(None))
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/health").status_code == 200
