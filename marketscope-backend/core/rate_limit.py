"""In-memory request limits. Enough for one server process; a restart clears them."""
import threading
import time
from collections import deque

from fastapi import HTTPException, Request

from core.config import IS_PRODUCTION


_MAX_TRACKED_KEYS = 50_000
_hits: dict[str, deque] = {}
_lock = threading.Lock()


def client_ip(request: Request) -> str:
    """The caller's address. Behind Render's proxy it's the first X-Forwarded-For entry.

    A caller can forge that header, so per-IP limits slow people down rather than
    stop them. Limits that matter most are also keyed on the email or user.
    """
    if IS_PRODUCTION:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _forget_idle_keys(now: float, window_seconds: int) -> None:
    for key in [key for key, hits in _hits.items() if not hits or now - hits[-1] > window_seconds]:
        del _hits[key]


def check_rate_limit(key: str, limit: int, window_seconds: int, message: str = "Too many attempts. Try again later.") -> None:
    """Counts one attempt for this key, or raises 429 when it's over the limit."""
    now = time.monotonic()
    with _lock:
        if len(_hits) > _MAX_TRACKED_KEYS:
            _forget_idle_keys(now, window_seconds)
        hits = _hits.setdefault(key, deque())
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            raise HTTPException(status_code=429, detail=message)
        hits.append(now)


def reset_rate_limits() -> None:
    with _lock:
        _hits.clear()
