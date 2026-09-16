"""Shared Redis client (OAuth state, rate limits, job queue).

Always call `get_redis()` at use time instead of caching the client in another module, so tests can
swap in fakeredis with `set_redis()`.
"""

import redis

from app.config import get_settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_timeout=3,
            socket_connect_timeout=3,
            health_check_interval=30,
        )
    return _client


def set_redis(client: redis.Redis | None) -> None:
    """Test hook: replace the process-wide client (None resets to a lazily created real client)."""
    global _client
    _client = client
