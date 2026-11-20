"""Server-side conversation memory.

The browser only holds an opaque random session id; the history lives here. Clients therefore cannot
inject fake assistant turns into the conversation, and each request carries one short message.
Bounded: sessions expire after a TTL, the oldest are evicted past a cap, and only recent turns are kept.
"""
from __future__ import annotations

import re
import secrets
import time
from collections import OrderedDict

from .config import settings

SID_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")


class SessionStore:
    def __init__(self, max_sessions: int | None = None, ttl: int | None = None, max_messages: int | None = None):
        self.max_sessions = max_sessions or settings.max_sessions
        self.ttl = ttl or settings.session_ttl
        self.max_messages = max_messages or settings.history_turns
        self._data: OrderedDict[str, tuple[float, list[dict]]] = OrderedDict()

    def _prune(self) -> None:
        now = time.time()
        for sid in [s for s, (t, _) in self._data.items() if now - t > self.ttl]:
            del self._data[sid]
        while len(self._data) > self.max_sessions:
            self._data.popitem(last=False)

    def get(self, sid: str | None) -> tuple[str, list[dict]]:
        """Return (session id, history). Unknown, expired or malformed ids get a fresh session."""
        self._prune()
        if sid and SID_RE.match(sid) and sid in self._data:
            self._data.move_to_end(sid)
            return sid, list(self._data[sid][1])
        return secrets.token_urlsafe(24), []

    def save(self, sid: str, history: list[dict]) -> None:
        self._data[sid] = (time.time(), history[-self.max_messages:])
        self._data.move_to_end(sid)
        self._prune()

    def reset(self, sid: str | None) -> None:
        if sid:
            self._data.pop(sid, None)

    def __len__(self) -> int:
        return len(self._data)
