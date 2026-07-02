"""CORS behavior at the HTTP boundary (Phase 10).

The middleware's origin list is read once at app startup, so these tests
exercise the *default* configuration (localhost dev origins) end-to-end via
TestClient, and the ALLOWED_ORIGINS parsing rules directly via the
`allowed_origins` helper.
"""

from fastapi.testclient import TestClient

from app.main import allowed_origins, app

client = TestClient(app)

ALLOWED_ORIGIN = "http://localhost:3000"
DISALLOWED_ORIGIN = "https://evil.example"


def _preflight(origin: str):
    return client.options(
        "/translate",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


def test_preflight_from_allowed_origin_passes() -> None:
    response = _preflight(ALLOWED_ORIGIN)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "POST" in response.headers["access-control-allow-methods"]


def test_preflight_from_disallowed_origin_lacks_cors_headers() -> None:
    response = _preflight(DISALLOWED_ORIGIN)
    assert "access-control-allow-origin" not in response.headers


def test_simple_request_from_allowed_origin_gets_cors_header() -> None:
    response = client.get("/health", headers={"Origin": ALLOWED_ORIGIN})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_simple_request_from_disallowed_origin_lacks_cors_header() -> None:
    response = client.get("/health", headers={"Origin": DISALLOWED_ORIGIN})
    # The request itself still succeeds (CORS is a browser-side gate); the
    # point is that no allow-origin header licenses the disallowed origin.
    assert "access-control-allow-origin" not in response.headers


# --- ALLOWED_ORIGINS parsing -------------------------------------------------


def test_unset_env_falls_back_to_dev_origins(monkeypatch) -> None:
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert allowed_origins() == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_env_is_parsed_comma_separated_with_whitespace_and_trailing_slash(monkeypatch) -> None:
    monkeypatch.setenv(
        "ALLOWED_ORIGINS", " https://nlsb.example.com/ , https://www.nlsb.example.com "
    )
    assert allowed_origins() == [
        "https://nlsb.example.com",
        "https://www.nlsb.example.com",
    ]


def test_wildcard_is_never_honored(monkeypatch) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    assert allowed_origins() == ["http://localhost:3000", "http://127.0.0.1:3000"]

    monkeypatch.setenv("ALLOWED_ORIGINS", "https://nlsb.example.com,*")
    assert allowed_origins() == ["https://nlsb.example.com"]
