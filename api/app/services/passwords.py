"""Account credential helpers: email normalisation and argon2id password hashing/policy."""

import re
import threading
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from pydantic import AfterValidator
from pydantic_core import PydanticCustomError

from app.errors import ApiError

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 1024

# argon2-cffi defaults are argon2id (RFC 9106 low-memory profile). Tests swap this for a cheaper one.
hasher = PasswordHasher()

# Each argon2 hash/verify allocates 64 MiB; unauthenticated login/signup must not be able to run an
# unbounded number at once (40 threadpool threads x 64 MiB OOMs the 768 MB container). Extra callers queue.
_hash_slots = threading.BoundedSemaphore(2)

_dummy_hash: str | None = None

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")


def normalize_email(value: str) -> str:
    return value.strip().lower()


def _validate_email(value: str) -> str:
    # Deliberately lenient (self-hosted installs use addresses like admin@home.lan).
    value = normalize_email(value)
    if len(value) > 255 or not _EMAIL_RE.match(value):
        raise PydanticCustomError("value_error", "Invalid email address")
    return value


Email = Annotated[str, AfterValidator(_validate_email)]


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ApiError(
            422,
            "validation_error",
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
            {"field": "password", "min_length": MIN_PASSWORD_LENGTH},
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ApiError(422, "validation_error", "Password is too long", {"field": "password"})


def hash_password(password: str) -> str:
    with _hash_slots:
        return hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-ish time: hashes against a dummy when the account has no password."""
    global _dummy_hash
    if not password_hash:
        if _dummy_hash is None:
            _dummy_hash = hash_password("dummy-password-for-timing")
        _verify(_dummy_hash, password)
        return False
    return _verify(password_hash, password)


def _verify(password_hash: str, password: str) -> bool:
    try:
        with _hash_slots:
            return hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False
