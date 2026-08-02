"""Phase 12E: server-side aggregate event counting.

`POST /events` is public and unauthenticated, so the tests that matter most
here are the ones that treat the client as hostile: an unknown event name, a
strategy description smuggled in a property, a nested structure, a giant body.
The frontend has its own sanitizer and it is a convenience -- anyone can post
here directly, so the server's allowlist is the actual boundary.

The read routes fail CLOSED: with `NLSB_EVENTS_TOKEN` unset they 404 rather
than serve data, because an unset secret must never mean "readable by anyone".
"""

from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient

from app import main
from app.storage import events as events_module
from app.storage.events import ALLOWED_EVENT_NAMES, event_store, sanitize_properties

STRATEGY_TEXT = "Buy SPY when RSI(14) drops below 30, sell when it rises above 70"


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    """A fresh database per test, never the real /data volume."""
    monkeypatch.setenv("NLSB_EVENTS_ENABLED", "true")
    monkeypatch.setenv("NLSB_DATA_DIR", str(tmp_path))
    event_store.reset_for_tests(tmp_path / "events.sqlite3")
    yield event_store
    event_store.reset_for_tests(None)


@pytest.fixture
def client():
    return TestClient(main.app)


def _post(client, payload, raw: str | None = None):
    # text/plain mirrors what navigator.sendBeacon actually sends.
    return client.post(
        "/events",
        content=raw if raw is not None else json.dumps(payload),
        headers={"Content-Type": "text/plain;charset=UTF-8"},
    )


def _rows() -> list[tuple]:
    # `configure()` explicitly: a rejected event never reaches the store, so
    # the table legitimately may not exist yet -- which is itself the correct
    # behavior (junk input must not cause a database to be created).
    event_store.configure()
    if not event_store.enabled:
        return []
    conn = event_store._connect()
    return conn.execute("SELECT name, occurred_at, properties FROM events").fetchall()


# --- TASK 1: ingest, and the allowlist as the security boundary -------------


def test_a_known_event_is_recorded(client):
    resp = _post(client, {"name": "gate_shown", "props": {}})

    assert resp.status_code == 202
    assert resp.json() == {"recorded": True}
    assert [r[0] for r in _rows()] == ["gate_shown"]


@pytest.mark.parametrize("name", sorted(ALLOWED_EVENT_NAMES))
def test_every_allowlisted_name_is_accepted(client, name):
    assert _post(client, {"name": name, "props": {}}).json()["recorded"] is True


@pytest.mark.parametrize(
    "name",
    ["", "admin", "drop_table", "gate_shown; DROP TABLE events", "GATE_SHOWN", "../../etc/passwd"],
)
def test_an_unknown_event_name_is_rejected_and_not_stored(client, name):
    resp = _post(client, {"name": name, "props": {}})

    assert resp.status_code == 202  # always success-shaped
    assert resp.json() == {"recorded": False}
    assert _rows() == []


def test_a_malformed_body_is_absorbed_without_an_error(client):
    for raw in ["not json at all", "[]", "null", '{"name": 42}', ""]:
        resp = _post(client, None, raw=raw)
        assert resp.status_code == 202
        assert resp.json() == {"recorded": False}
    assert _rows() == []


def test_an_oversized_body_is_rejected(client):
    resp = _post(client, {"name": "gate_shown", "props": {"pad": "x" * 20000}})

    assert resp.status_code == 202
    assert resp.json()["recorded"] is False
    assert _rows() == []


# --- INVARIANT: nothing identifying is ever stored --------------------------


def test_strategy_text_in_a_property_is_dropped_not_stored(client):
    _post(client, {"name": "strategy_submitted", "props": {"nlText": STRATEGY_TEXT}})

    stored = json.loads(_rows()[0][2])
    assert stored == {}
    assert STRATEGY_TEXT not in _rows()[0][2]


def test_the_stored_row_shape_contains_no_identity(client):
    """INV: there is no column from which an individual's session could be
    reconstructed. Pinned against the schema, not just against one payload."""
    _post(
        client,
        {"name": "result_shown", "props": {"verdict": "PASS"}},
        raw=None,
    )
    conn = event_store._connect()
    columns = [row[1] for row in conn.execute("PRAGMA table_info(events)")]

    assert columns == ["id", "name", "occurred_at", "properties"]
    for forbidden in ("ip", "addr", "agent", "session", "user", "cookie", "referer"):
        assert not any(forbidden in c.lower() for c in columns)


def test_the_client_ip_and_user_agent_are_never_persisted(client):
    client.post(
        "/events",
        content=json.dumps({"name": "gate_shown", "props": {}}),
        headers={
            "Content-Type": "text/plain",
            "X-Forwarded-For": "203.0.113.7",
            "User-Agent": "Mozilla/5.0 (a very identifying string)",
        },
    )

    blob = json.dumps(_rows())
    assert "203.0.113.7" not in blob
    assert "Mozilla" not in blob


def test_nested_structures_and_long_strings_are_dropped():
    clean = sanitize_properties(
        {
            "verdict": "PASS",
            "status": 429,
            "ok": False,
            "nothing": None,
            "nested": {"a": 1},
            "list": [1, 2, 3],
            "essay": "x" * 41,
        }
    )
    assert clean == {"verdict": "PASS", "status": 429, "ok": False, "nothing": None}


def test_the_property_bag_is_capped():
    clean = sanitize_properties({f"k{i}": i for i in range(50)})
    assert len(clean) <= 12


def test_a_non_dict_property_bag_is_absorbed():
    assert sanitize_properties("nope") == {}
    assert sanitize_properties(None) == {}
    assert sanitize_properties([1, 2]) == {}


# --- TASK 2: storage behavior -----------------------------------------------


def test_concurrent_writes_from_many_threads_all_land():
    """Handlers run in anyio's 40-thread pool, so the store has to be correct
    under real concurrent threads, not merely serialized calls."""
    n = 40
    ready = threading.Barrier(n)

    def _worker():
        ready.wait()
        event_store.record("gate_shown", {"i": 1})

    threads = [threading.Thread(target=_worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert event_store.summary()["totals"]["gate_shown"] == n


def test_an_unwritable_data_dir_disables_recording_without_breaking_routes(
    client, monkeypatch, tmp_path
):
    # Point both the configured dir and the fallback at something unusable.
    monkeypatch.setattr(events_module, "_LOCAL_FALLBACK", tmp_path / "nope" / "deeper")
    monkeypatch.setattr(EventStoreProbe := events_module.EventStore, "_resolve_path", lambda self: None)
    event_store.reset_for_tests(None)

    resp = _post(client, {"name": "gate_shown", "props": {}})
    assert resp.status_code == 202
    assert resp.json() == {"recorded": False}

    # Every other route keeps working -- losing counts must never take the app
    # down because a volume was not mounted.
    assert client.get("/health").status_code == 200
    assert event_store.summary()["storage_enabled"] is False
    assert EventStoreProbe is events_module.EventStore


def test_recording_can_be_switched_off(client, monkeypatch):
    monkeypatch.setenv("NLSB_EVENTS_ENABLED", "false")

    assert _post(client, {"name": "gate_shown", "props": {}}).json()["recorded"] is False
    assert _rows() == []


# --- TASK 3: the read path, failing closed ----------------------------------


def test_read_routes_404_when_the_token_env_is_unset(client, monkeypatch):
    monkeypatch.delenv("NLSB_EVENTS_TOKEN", raising=False)

    assert client.get("/events/summary").status_code == 404
    assert client.get("/events/summary/page").status_code == 404


def test_read_routes_404_without_a_token(client, monkeypatch):
    monkeypatch.setenv("NLSB_EVENTS_TOKEN", "s3cret")

    assert client.get("/events/summary").status_code == 404
    assert client.get("/events/summary/page").status_code == 404


def test_read_routes_404_with_the_wrong_token_and_leak_no_data(client, monkeypatch):
    monkeypatch.setenv("NLSB_EVENTS_TOKEN", "s3cret")
    _post(client, {"name": "gate_shown", "props": {}})

    resp = client.get("/events/summary?token=wrong")
    assert resp.status_code == 404
    assert "gate_shown" not in resp.text


def test_the_token_is_accepted_by_query_or_header(client, monkeypatch):
    monkeypatch.setenv("NLSB_EVENTS_TOKEN", "s3cret")
    _post(client, {"name": "gate_shown", "props": {}})

    assert client.get("/events/summary?token=s3cret").status_code == 200
    assert client.get("/events/summary", headers={"X-Events-Token": "s3cret"}).status_code == 200


def test_summary_aggregates_and_derives_the_numbers_worth_reading(client, monkeypatch):
    monkeypatch.setenv("NLSB_EVENTS_TOKEN", "s3cret")
    for _ in range(10):
        _post(client, {"name": "gate_shown", "props": {}})
    for _ in range(4):
        _post(client, {"name": "gate_confirmed", "props": {}})
    for _ in range(6):
        _post(client, {"name": "gate_abandoned", "props": {}})
    for _ in range(3):
        _post(client, {"name": "result_shown", "props": {"verdict": "PASS"}})

    body = client.get("/events/summary?token=s3cret").json()

    assert body["totals"] == {
        "gate_abandoned": 6,
        "gate_confirmed": 4,
        "gate_shown": 10,
        "result_shown": 3,
    }
    # Explicit fields, so reading them takes no arithmetic on a phone.
    assert body["total_backtests_completed"] == 3
    assert body["gate_confirm_rate"] == 0.4
    assert body["total_events"] == 23
    assert body["daily"][0]["counts"]["gate_shown"] == 10


def test_an_unseen_gate_reports_an_unknown_rate_not_zero(client, monkeypatch):
    monkeypatch.setenv("NLSB_EVENTS_TOKEN", "s3cret")

    body = client.get("/events/summary?token=s3cret").json()

    # A rate with no denominator is unknown; 0% would be a claim.
    assert body["gate_confirm_rate"] is None


def test_the_summary_window_is_bounded(client, monkeypatch):
    monkeypatch.setenv("NLSB_EVENTS_TOKEN", "s3cret")

    assert client.get("/events/summary?token=s3cret&days=99999").json()["days"] == 365
    assert client.get("/events/summary?token=s3cret&days=0").json()["days"] == 1


def test_the_html_page_renders_the_same_numbers(client, monkeypatch):
    monkeypatch.setenv("NLSB_EVENTS_TOKEN", "s3cret")
    for _ in range(2):
        _post(client, {"name": "gate_shown", "props": {}})
    _post(client, {"name": "gate_confirmed", "props": {}})

    resp = client.get("/events/summary/page?token=s3cret")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Gate confirm rate" in resp.text
    assert "50.0%" in resp.text
    assert "noindex" in resp.text
    # No client JS: this page must keep working when everything else doesn't.
    assert "<script" not in resp.text.lower()


# --- INVARIANTS -------------------------------------------------------------


def test_events_never_touch_the_llm_or_the_spend_breaker(client, monkeypatch):
    from app import abuse

    abuse.spend_breaker.reset()

    def _explode():
        raise AssertionError("/events must never construct an LLM client")

    monkeypatch.setattr("app.translation.service._default_llm_client", _explode)

    for name in sorted(ALLOWED_EVENT_NAMES):
        assert _post(client, {"name": name, "props": {}}).status_code == 202

    assert abuse.spend_breaker.count == 0


def test_events_never_trigger_a_backtest(client, monkeypatch):
    def _explode(*args, **kwargs):
        raise AssertionError("/events must never run a backtest")

    monkeypatch.setattr("app.translation.service.run_ir_backtest", _explode)
    monkeypatch.setattr("app.translation.service.run_robustness", _explode)

    assert _post(client, {"name": "result_shown", "props": {}}).status_code == 202


def test_events_are_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setenv("NLSB_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("NLSB_RATE_LIMIT_EVENTS_PER_MIN", "3")

    statuses = []
    for _ in range(12):
        statuses.append(_post(client, {"name": "gate_shown", "props": {}}).status_code)
        if statuses[-1] == 429:
            break

    assert 429 in statuses, "the ingest endpoint must not be an unbounded write"
