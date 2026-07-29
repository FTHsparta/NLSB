"""Bounded in-process cache for successful NL -> IR translations.

Purpose is cost, not speed: an identical strategy description costs up to
`MAX_RETRIES` billable Anthropic calls every time it is submitted, and the
landing page ships four fixed example strings that many visitors will send
verbatim. A hit skips the model entirely.

NOT A TRUST BOUNDARY. A cached IR is exactly as untrusted as a fresh one:
`app.translation.service` re-runs the full schema validator on every hit
before the entry is returned, and evicts anything that no longer validates.
Nothing here weakens the security boundary -- the LLM still emits only
validated IR JSON, and no model-emitted content is ever executed.

Bounded size is itself a security property. An unbounded map keyed on
arbitrary user text is a memory-exhaustion primitive: anyone could push
distinct strings until the process dies. `NLSB_TRANSLATION_CACHE_SIZE` caps
the entry count and the oldest entry is evicted on overflow.

Every knob reads its environment variable at call time, matching the rest of
the NLSB_* config style (see `app.abuse`).
"""

from __future__ import annotations

import copy
import hashlib
import logging
import os
import re
import threading
from collections import OrderedDict
from typing import TypeVar

logger = logging.getLogger("app.translation.cache")

T = TypeVar("T")

_WHITESPACE = re.compile(r"\s+")


def cache_enabled() -> bool:
    return os.environ.get("NLSB_TRANSLATION_CACHE_ENABLED", "true").lower() == "true"


def cache_size() -> int:
    return int(os.environ.get("NLSB_TRANSLATION_CACHE_SIZE", "512"))


def normalize(nl_text: str) -> str:
    """Collapse the differences that don't change what was asked.

    Leading/trailing space, runs of internal whitespace (including the
    newlines a paste introduces), and case. Deliberately conservative: it
    never touches punctuation or word order, so two genuinely different
    strategies can't normalize together.
    """
    return _WHITESPACE.sub(" ", nl_text.strip()).casefold()


def cache_key(nl_text: str, *, model: str, version: int) -> str:
    """Hash of the normalized request, the model, and the prompt/schema
    version. The version is what retires every entry at once when the system
    prompt or the IR schema changes; the model is in the key because two
    models are entitled to translate the same sentence differently.

    Hashing rather than storing raw text keeps unbounded user input out of
    the key space, and the separator can't be produced by any of the parts.
    """
    raw = "\x1f".join((normalize(nl_text), model, str(version)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TranslationCache:
    """Thread-safe bounded LRU. Handlers are sync `def` and run in anyio's
    thread pool, so every operation here is genuinely concurrent."""

    def __init__(self) -> None:
        self._entries: OrderedDict[str, object] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> object | None:
        """Return a DEEP COPY of the cached value, or None.

        The copy is not paranoia: callers hand the result to route code that
        may mutate the IR dict or the assumptions list, and a shared object
        would let one request corrupt every later hit.
        """
        if not cache_enabled():
            return None
        with self._lock:
            if key not in self._entries:
                return None
            self._entries.move_to_end(key)
            value = self._entries[key]
        return copy.deepcopy(value)

    def put(self, key: str, value: object) -> None:
        """Store a deep copy, evicting the least-recently-used entry when the
        configured size is exceeded."""
        if not cache_enabled():
            return
        stored = copy.deepcopy(value)
        limit = max(0, cache_size())
        with self._lock:
            if limit == 0:
                return
            self._entries[key] = stored
            self._entries.move_to_end(key)
            while len(self._entries) > limit:
                evicted, _ = self._entries.popitem(last=False)
                logger.debug("translation cache evicted %s (size limit %d)", evicted[:12], limit)

    def evict(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        """For tests only: the cache is process-global and would otherwise
        leak entries between cases."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


translation_cache = TranslationCache()
