"""Fixed-window rate limits in Redis."""

import logging

from app.crypto import sha256_hex
from app.errors import ApiError
from app.redis_client import get_redis

log = logging.getLogger(__name__)

LOGIN_LIMIT = 10
LOGIN_WINDOW_SECONDS = 15 * 60


def hit(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Counts one attempt. Returns (allowed, retry_after_seconds).

    Fails open (allowed) if Redis is unreachable, so a Redis outage can't lock everyone out.
    """
    redis = get_redis()
    try:
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds, nx=True)
        pipe.ttl(key)
        count, _, ttl = pipe.execute()
    except Exception:  # noqa: BLE001
        log.warning("Rate limit check skipped: Redis unavailable", exc_info=True)
        return True, 0
    return int(count) <= limit, max(int(ttl), 0)


def reset(key: str) -> None:
    try:
        get_redis().delete(key)
    except Exception:  # noqa: BLE001
        log.warning("Rate limit reset skipped: Redis unavailable", exc_info=True)


def login_key(ip: str | None, email: str) -> str:
    return "rl:login:" + sha256_hex(f"{ip or '-'}|{email}")


def check_login(ip: str | None, email: str) -> None:
    allowed, retry_after = hit(login_key(ip, email), LOGIN_LIMIT, LOGIN_WINDOW_SECONDS)
    if not allowed:
        raise ApiError(
            429,
            "rate_limited",
            "Too many sign-in attempts. Try again later.",
            {"retry_after": retry_after},
        )
