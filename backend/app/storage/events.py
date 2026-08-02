"""Aggregate funnel-event counting. SQLite, append-only, no identities.

WHAT THIS IS NOT: user tracking. Nothing here stores an IP address, a user
agent, a session id, a cookie, or any free text. A row is an event name, a
UTC timestamp, and a small bag of bounded scalars -- by construction there is
no column from which an individual's session could be reconstructed, which is
why the sanitizer is a whitelist on value SHAPE rather than a blacklist of
fields someone remembered to exclude.

The ingest endpoint this backs is PUBLIC and UNAUTHENTICATED, so every field
arriving from a client is hostile input. `ALLOWED_EVENT_NAMES` is the security
boundary: an unrecognized name is rejected rather than stored, so the table's
contents are drawn from a fixed vocabulary this repo controls. The frontend
has its own sanitizer, and that one is a convenience -- a client is free not
to run it. This one is the boundary.

Every knob reads its environment variable at call time, matching the NLSB_*
config style in `app.abuse`.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("app.storage.events")

# The complete vocabulary. Anything else is refused at the door.
ALLOWED_EVENT_NAMES: frozenset[str] = frozenset(
    {
        "example_clicked",
        "strategy_submitted",
        "gate_shown",
        "gate_confirmed",
        "gate_abandoned",
        "result_shown",
        "request_failed",
    }
)

# Mirrors the frontend's `sanitizeProps` limits. Deliberately duplicated
# rather than shared: the client's copy can be bypassed by anyone posting
# directly, so these have to hold independently.
MAX_STRING_LENGTH = 40
MAX_KEY_LENGTH = 40
MAX_PROPERTIES = 12

# Bound on the read path so a summary can't be turned into an expensive scan.
MAX_SUMMARY_DAYS = 365
DEFAULT_SUMMARY_DAYS = 30

_LOCAL_FALLBACK = Path(__file__).resolve().parents[1] / "data" / "cache"


def events_enabled() -> bool:
    return os.environ.get("NLSB_EVENTS_ENABLED", "true").lower() == "true"


def configured_data_dir() -> str:
    """Where the database lives. On Railway this must match the volume's
    mount path -- without a volume the file is ephemeral and every deploy
    starts the counts over."""
    return os.environ.get("NLSB_DATA_DIR", "/data")


def events_token() -> str | None:
    """Shared secret for the read routes. Unset means the read surface does
    not exist at all (fail closed), never 'open to everyone'."""
    token = os.environ.get("NLSB_EVENTS_TOKEN", "").strip()
    return token or None


def sanitize_properties(props: object) -> dict:
    """Keep only bounded scalars, drop everything else.

    Nested structures, long strings, and oversized bags are dropped rather
    than rejected outright: a client sending one odd property should still
    have its event counted, since the count is the point and the property is
    a nicety. What must never happen is storing the odd property.
    """
    if not isinstance(props, dict):
        return {}
    clean: dict = {}
    for key, value in props.items():
        if len(clean) >= MAX_PROPERTIES:
            break
        if not isinstance(key, str) or not key or len(key) > MAX_KEY_LENGTH:
            continue
        # bool before int: bool is a subclass of int and both are fine here,
        # but the ordering keeps the intent explicit.
        if value is None or isinstance(value, (bool, int, float)):
            clean[key] = value
            continue
        if isinstance(value, str) and 0 < len(value) <= MAX_STRING_LENGTH:
            clean[key] = value
        # dicts, lists, and over-long strings fall through and are dropped.
    return clean


class EventStore:
    """Append-only counter backed by SQLite.

    One connection PER THREAD (`threading.local`). Route handlers run in
    anyio's 40-thread pool, and a sqlite3 connection is not meant to be
    shared across threads; a per-thread connection sidesteps that entirely
    and avoids a global write lock in Python. WAL mode plus a busy timeout is
    what makes concurrent writers safe at the SQLite level.

    If the database cannot be opened the store DISABLES itself and logs
    loudly. Losing counts is acceptable; taking the app down because a volume
    was not mounted is not -- /translate and /confirm must keep working.
    """

    def __init__(self) -> None:
        self._local = threading.local()
        self._path: Path | None = None
        self._disabled = False
        self._ready = False
        self._init_lock = threading.Lock()

    # --- setup ---

    def _resolve_path(self) -> Path | None:
        """Preferred directory, else a local gitignored fallback, else None.

        The fallback is what keeps dev and CI from depending on a Railway
        volume existing: an unwritable /data is the NORMAL case off-platform,
        not an error worth failing on.
        """
        for candidate in (Path(configured_data_dir()), _LOCAL_FALLBACK):
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                probe = candidate / ".write-probe"
                probe.touch()
                probe.unlink()
                return candidate / "events.sqlite3"
            except OSError:
                continue
        return None

    def configure(self) -> None:
        """Create the table if absent. Safe to call repeatedly; never raises."""
        with self._init_lock:
            if self._disabled or self._ready:
                return
            path = self._path or self._resolve_path()
            if path is None:
                self._disabled = True
                logger.error(
                    "event storage disabled: no writable data directory (tried %r and %r). "
                    "Counts will not be recorded; every other route is unaffected.",
                    configured_data_dir(),
                    str(_LOCAL_FALLBACK),
                )
                return
            self._path = path
            try:
                conn = self._connect()
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        properties TEXT NOT NULL
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_name ON events(name)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_time ON events(occurred_at)")
                conn.commit()
                self._ready = True
                logger.info("event storage ready at %s", path)
            except sqlite3.Error:
                self._disabled = True
                self._path = None
                logger.exception("event storage disabled: could not initialize the database")

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            assert self._path is not None
            conn = sqlite3.connect(str(self._path), timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    @property
    def enabled(self) -> bool:
        return not self._disabled and self._ready

    # --- write ---

    def record(self, name: str, properties: dict) -> bool:
        """Append one event. Returns whether it was stored.

        Never raises: the caller is an endpoint whose entire contract is to
        be cheap and to never surface a failure. A dropped count is strictly
        better than a 500 on a beacon.
        """
        if not events_enabled():
            return False
        if name not in ALLOWED_EVENT_NAMES:
            return False
        self.configure()
        if not self.enabled:
            return False
        try:
            conn = self._connect()
            conn.execute(
                "INSERT INTO events (name, occurred_at, properties) VALUES (?, ?, ?)",
                (
                    name,
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(sanitize_properties(properties), separators=(",", ":")),
                ),
            )
            conn.commit()
            return True
        except sqlite3.Error:
            logger.warning("failed to record event %r", name, exc_info=True)
            return False

    # --- read ---

    def summary(self, days: int = DEFAULT_SUMMARY_DAYS) -> dict:
        """Aggregate counts plus the two numbers actually worth reading.

        `gate_confirm_rate` and `total_backtests_completed` are emitted as
        explicit fields rather than left as arithmetic on the totals -- the
        whole point of the read surface is answering a question without
        doing mental math on a phone.
        """
        days = max(1, min(int(days), MAX_SUMMARY_DAYS))
        empty = {
            "days": days,
            "totals": {},
            "daily": [],
            "total_events": 0,
            "total_backtests_completed": 0,
            "gate_shown": 0,
            "gate_confirmed": 0,
            "gate_abandoned": 0,
            "gate_confirm_rate": None,
            "storage_enabled": self.enabled,
        }
        self.configure()
        if not self.enabled:
            return empty

        try:
            conn = self._connect()
            totals = {
                row[0]: row[1]
                for row in conn.execute("SELECT name, COUNT(*) FROM events GROUP BY name")
            }
            daily_rows = conn.execute(
                """
                SELECT substr(occurred_at, 1, 10) AS day, name, COUNT(*)
                FROM events
                WHERE substr(occurred_at, 1, 10) >= date('now', ?)
                GROUP BY day, name
                ORDER BY day DESC, name ASC
                """,
                (f"-{days} days",),
            ).fetchall()
        except sqlite3.Error:
            logger.exception("failed to read event summary")
            return empty

        by_day: dict[str, dict[str, int]] = {}
        for day, name, count in daily_rows:
            by_day.setdefault(day, {})[name] = count

        shown = int(totals.get("gate_shown", 0))
        confirmed = int(totals.get("gate_confirmed", 0))
        return {
            "days": days,
            "totals": dict(sorted(totals.items())),
            "daily": [{"day": day, "counts": by_day[day]} for day in sorted(by_day, reverse=True)],
            "total_events": sum(totals.values()),
            "total_backtests_completed": int(totals.get("result_shown", 0)),
            "gate_shown": shown,
            "gate_confirmed": confirmed,
            "gate_abandoned": int(totals.get("gate_abandoned", 0)),
            # None, not 0, when nobody has seen the gate: a rate with no
            # denominator is unknown, and reporting it as 0% would be a claim.
            "gate_confirm_rate": round(confirmed / shown, 4) if shown else None,
            "storage_enabled": True,
        }

    # --- test support ---

    def reset_for_tests(self, path: Path | None = None) -> None:
        """Point the store at a fresh database (or re-resolve). Closes any
        per-thread connections this thread holds."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
            self._local.conn = None
        self._local = threading.local()
        self._path = path
        self._disabled = False
        self._ready = False


event_store = EventStore()
