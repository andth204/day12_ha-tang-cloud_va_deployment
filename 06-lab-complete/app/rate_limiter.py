"""Sliding-window rate limiter (in-memory, per API key)."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException

from app.config import settings

_rate_windows: dict[str, deque] = defaultdict(deque)


def check_rate_limit(key: str) -> None:
    """
    Sliding-window counter: allow at most settings.rate_limit_per_minute
    requests per 60-second window per key.

    Raises HTTP 429 with Retry-After header when limit is exceeded.
    """
    now = time.time()
    window = _rate_windows[key]

    # Discard timestamps older than 60 seconds
    while window and window[0] < now - 60:
        window.popleft()

    if len(window) >= settings.rate_limit_per_minute:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
            headers={"Retry-After": "60"},
        )

    window.append(now)
