"""Rate limiting configuration using slowapi."""

import threading
import time
from collections import defaultdict, deque

from slowapi import Limiter
from slowapi.util import get_remote_address


def get_client_ip(request) -> str:
    """Best-effort real client IP for rate limiting and audit logging.

    The app is intended to run behind a reverse proxy (Cloudflare). Cloudflare
    sets ``CF-Connecting-IP`` and overwrites it on every request, so it is the
    trustworthy source when present. We fall back to the first ``X-Forwarded-For``
    hop, then the direct peer. Without ``CF-Connecting-IP``/XFF spoofing
    mitigation a determined client could spoof XFF, but for a single-user
    self-hosted app this is acceptable and far better than bucketing every
    client behind the proxy into one shared limit.
    """
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


# Create limiter instance keyed on the resolved client IP.
limiter = Limiter(key_func=get_client_ip)


class SlidingWindowThrottle:
    """Tiny in-memory per-key sliding-window throttle (thread-safe).

    Used to brute-force/DoS-protect the bearer-token (bot API key) and MCP auth
    paths, which slowapi's route decorators don't cover. Process-local, which is
    fine for the single-worker deployment.
    """

    def __init__(self, max_events: int, window_seconds: float):
        self.max_events = max_events
        self.window = window_seconds
        self._events: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_blocked(self, key: str) -> bool:
        """True if this key has hit the limit within the window."""
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            events = self._events[key]
            while events and events[0] < cutoff:
                events.popleft()
            if not events:
                # Opportunistically drop the empty bucket to bound memory.
                self._events.pop(key, None)
                return False
            return len(events) >= self.max_events

    def record_failure(self, key: str) -> None:
        """Record one failed attempt for this key."""
        now = time.monotonic()
        with self._lock:
            self._events[key].append(now)


# Throttle failed bearer/MCP auth attempts: 20 failures per minute per IP.
bearer_auth_throttle = SlidingWindowThrottle(max_events=20, window_seconds=60.0)
