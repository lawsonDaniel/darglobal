"""HTTP-level protections: client IP resolution, rate and cost limits, body size cap, security headers."""
from __future__ import annotations

import asyncio
import hashlib
import time
from collections import defaultdict, deque

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import settings

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
SECURITY_HEADERS = [
    (b"content-security-policy", CSP.encode()),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
]


def client_ip(headers: dict[str, str], peer: str | None, hops: int | None = None) -> str:
    """The client address as seen by the outermost trusted proxy.

    X-Forwarded-For is client-controlled except for the entries our own proxies append, so we take the
    entry `hops` places from the right (Render's proxy = 1 hop). hops=0 ignores the header entirely.
    """
    hops = settings.trusted_proxy_hops if hops is None else hops
    xff = headers.get("x-forwarded-for", "")
    if hops > 0 and xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return peer or "unknown"


def ip_tag(ip: str) -> str:
    """Short hash for logs, so raw IP addresses are not written to logs."""
    return hashlib.sha256(ip.encode()).hexdigest()[:10]


class RateLimiter:
    """Sliding-window limits per IP (minute and day) plus a global daily cap that protects the free model quota."""

    def __init__(self, per_minute: int | None = None, per_day: int | None = None, global_day: int | None = None):
        self.per_minute = per_minute or settings.rate_per_minute
        self.per_day = per_day or settings.rate_per_day
        self.global_day = global_day or settings.global_per_day
        self._minute: dict[str, deque] = defaultdict(deque)
        self._day: dict[str, deque] = defaultdict(deque)
        self._global: deque = deque()

    @staticmethod
    def _trim(q: deque, now: float, window: float) -> None:
        while q and now - q[0] > window:
            q.popleft()

    def check(self, ip: str, now: float | None = None) -> str | None:
        """Record a hit; return None if allowed, else the reason it is refused."""
        now = now or time.time()
        m, d = self._minute[ip], self._day[ip]
        self._trim(m, now, 60)
        self._trim(d, now, 86400)
        self._trim(self._global, now, 86400)
        if len(self._global) >= self.global_day:
            return "The assistant has reached its daily limit. Please try again tomorrow."
        if len(m) >= self.per_minute:
            return "Too many messages. Please wait a minute."
        if len(d) >= self.per_day:
            return "Daily message limit reached for your connection. Please try again tomorrow."
        m.append(now)
        d.append(now)
        self._global.append(now)
        if len(self._minute) > 10000:  # bound memory under address-rotation abuse
            for k in [k for k, q in self._minute.items() if not q][:5000]:
                self._minute.pop(k, None)
                self._day.pop(k, None)
        return None


class ConcurrencyGate:
    def __init__(self, limit: int | None = None):
        self.sem = asyncio.Semaphore(limit or settings.max_concurrent)

    async def acquire(self, wait: float = 15.0) -> bool:
        try:
            await asyncio.wait_for(self.sem.acquire(), timeout=wait)
            return True
        except asyncio.TimeoutError:
            return False

    def release(self) -> None:
        self.sem.release()


class SecurityMiddleware:
    """Pure ASGI: adds security headers to every response and caps request body size."""

    def __init__(self, app: ASGIApp, max_body: int | None = None):
        self.app = app
        self.max_body = max_body or settings.max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [h for h in message.get("headers", []) if h[0].lower() != b"server"]
                headers += SECURITY_HEADERS
                if scope.get("path", "").startswith("/api/"):
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        length = dict(scope.get("headers") or []).get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > self.max_body):
            await self._reject(send_with_headers)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body:
                    raise _TooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send_with_headers)
        except _TooLarge:
            await self._reject(send_with_headers)

    @staticmethod
    async def _reject(send) -> None:
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b'{"error":"Request too large."}'})


class _TooLarge(Exception):
    pass
