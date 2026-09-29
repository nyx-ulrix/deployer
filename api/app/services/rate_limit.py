"""Fixed-window rate limits in Redis."""

import logging

from app.crypto import sha256_hex
from app.errors import ApiError
from app.redis_client import get_redis

log = logging.getLogger(__name__)

LOGIN_LIMIT = 10
LOGIN_WINDOW_SECONDS = 15 * 60
# Per-IP cap on password logins + signups (each costs an argon2 hash), across all emails.
LOGIN_IP_LIMIT = 30
# Per-email cap across every source IP (A-019): source IPs are cheap to rotate, and on :8080 every LAN
# client arrives with the same one. Cleared by a successful sign-in and by `deployer reset-password`.
LOGIN_EMAIL_LIMIT = 50
LOGIN_EMAIL_WINDOW_SECONDS = 3600


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


def reset_logins() -> None:
    """Clears every sign-in bucket. Run after a password reset on the Deployer PC: whoever forgot
    their password has usually used up their attempts, and would otherwise wait out the window."""
    try:
        redis = get_redis()
        keys = list(redis.scan_iter("rl:login*"))
        if keys:
            redis.delete(*keys)
    except Exception:  # noqa: BLE001
        log.warning("Rate limit reset skipped: Redis unavailable", exc_info=True)


def login_key(ip: str | None, email: str) -> str:
    return "rl:login:" + sha256_hex(f"{ip or '-'}|{email}")


def login_email_key(email: str) -> str:
    return "rl:login-email:" + sha256_hex(email)


def clear_login(ip: str | None, email: str) -> None:
    """After a successful sign-in: the email's attempts no longer count against it."""
    reset(login_key(ip, email))
    reset(login_email_key(email))


def check_login(ip: str | None, email: str | None = None) -> None:
    """Per-IP bucket for every attempt; with an email, also a per-(ip,email) bucket and a per-email one
    (every IP together), both cleared on success so only failures since the last sign-in count."""
    allowed, retry_after = hit(f"rl:login-ip:{ip or '-'}", LOGIN_IP_LIMIT, LOGIN_WINDOW_SECONDS)
    if allowed and email is not None:
        allowed, retry_after = hit(login_key(ip, email), LOGIN_LIMIT, LOGIN_WINDOW_SECONDS)
    if allowed and email is not None:
        allowed, retry_after = hit(login_email_key(email), LOGIN_EMAIL_LIMIT, LOGIN_EMAIL_WINDOW_SECONDS)
    if not allowed:
        raise ApiError(
            429,
            "rate_limited",
            "Too many sign-in attempts. Try again later.",
            {"retry_after": retry_after},
        )
