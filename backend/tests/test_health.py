from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# A fake key with distinctive characters that cannot collide with any word in
# the legitimate response body ("status", "ok", "anthropic_key_present", ...).
FAKE_KEY = "sk-ant-XQZV7WJ4YB9GPHRM2TKD8FNC3"


def test_health() -> None:
    """Phase 10: /health carries a readiness boolean for platform checks.
    (Pre-Phase-10 this asserted the exact body {"status": "ok"}; the shape
    change here is the deliberate Task-3 contract change, not drift.)"""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["anthropic_key_present"], bool)


def test_health_reports_key_presence_as_boolean(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    assert client.get("/health").json()["anthropic_key_present"] is True

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert client.get("/health").json()["anthropic_key_present"] is False


def test_health_never_leaks_any_substring_of_the_key(monkeypatch) -> None:
    """INV-2: no substring of the configured key (length >= 4, long enough to
    be non-coincidental) may appear anywhere in the raw response."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    response = client.get("/health")
    assert response.status_code == 200
    raw = response.text
    for i in range(len(FAKE_KEY) - 3):
        window = FAKE_KEY[i : i + 4]
        assert window not in raw, f"key fragment {window!r} leaked into /health"
