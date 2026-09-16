"""Encryption helpers.

- `encrypt_secret` / `decrypt_secret`: AES-256-GCM with the instance MASTER_KEY, for secrets stored
  in the platform database (OAuth client secrets, external database credentials).
- `encrypt_with_passphrase` / `decrypt_with_passphrase`: scrypt + AES-256-GCM, for export files.
"""

import base64
import hashlib
import json
import os
import secrets
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

_VERSION_PREFIX = "v1:"


def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def _master_key() -> bytes:
    raw = get_settings().master_key
    if not raw:
        raise RuntimeError("MASTER_KEY is not set")
    key = _b64d(raw)
    if len(key) != 32:
        raise RuntimeError("MASTER_KEY must be base64 of exactly 32 bytes")
    return key


def encrypt_secret(plaintext: str) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_master_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return _VERSION_PREFIX + _b64e(nonce + ciphertext)


def decrypt_secret(token: str) -> str:
    if not token.startswith(_VERSION_PREFIX):
        raise ValueError("Unknown secret format")
    blob = _b64d(token[len(_VERSION_PREFIX):])
    return AESGCM(_master_key()).decrypt(blob[:12], blob[12:], None).decode("utf-8")


def encrypt_json(value: Any) -> str:
    return encrypt_secret(json.dumps(value, separators=(",", ":")))


def decrypt_json(token: str) -> Any:
    return json.loads(decrypt_secret(token))


SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**15, 8, 1


def _derive(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        passphrase.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=128 * 1024 * 1024
    )


def encrypt_with_passphrase(plaintext: bytes, passphrase: str) -> tuple[dict[str, Any], str]:
    """Returns (encryption header, base64 ciphertext)."""
    salt, nonce = os.urandom(16), os.urandom(12)
    key = _derive(passphrase, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    header = {
        "cipher": "AES-256-GCM",
        "kdf": "scrypt",
        "n": SCRYPT_N,
        "r": SCRYPT_R,
        "p": SCRYPT_P,
        "salt": _b64e(salt),
        "nonce": _b64e(nonce),
    }
    return header, _b64e(ciphertext)


def decrypt_with_passphrase(header: dict[str, Any], payload_b64: str, passphrase: str) -> bytes:
    """Raises cryptography.exceptions.InvalidTag on a wrong passphrase."""
    if header.get("cipher") != "AES-256-GCM" or header.get("kdf") != "scrypt":
        raise ValueError("Unsupported export encryption")
    key = _derive(passphrase, _b64d(header["salt"]), int(header["n"]), int(header["r"]), int(header["p"]))
    return AESGCM(key).decrypt(_b64d(header["nonce"]), _b64d(payload_b64), None)


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
