"""Streaming encryption for backup artifacts (docs/BACKUPS.md "Storage & encryption").

File format (all integers big-endian)::

    magic      6 bytes  b"DPLBK1"
    key_id     8 bytes  first 8 bytes of SHA-256(backup key) - picks the key when several are known
    salt      16 bytes  random per file; file key = HKDF-SHA256(backup key, salt, info="deployer-backups-v1 file")
    nonce_pfx  7 bytes  random per file
    chunks...           AES-256-GCM(file key, nonce = nonce_pfx || counter(4) || last_flag(1), chunk, aad=header)

Every plaintext chunk is `CHUNK_SIZE` (1 MiB) except the last one, which may be shorter or empty and
is sealed with `last_flag = 1` (the STREAM construction of Hoang, Reyhanitabar, Rogaway & Vizar).
Truncation, reordering, chunk duplication and header tampering are all detected. The 37-byte header
is authenticated as associated data of every chunk.

The backup key is derived from MASTER_KEY: HKDF-SHA256(master key, salt=b"", info="deployer-backups-v1").
Instances restored from an export with a different MASTER_KEY keep reading old artifacts through
imported key material (`import_key_material`, stored in `<BACKUP_DIR>/.keys` encrypted with the
current MASTER_KEY).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.crypto import _master_key, decrypt_secret, encrypt_secret

MAGIC = b"DPLBK1"
HEADER_SIZE = len(MAGIC) + 8 + 16 + 7
CHUNK_SIZE = 1 << 20
TAG_SIZE = 16
BACKUP_KEY_INFO = b"deployer-backups-v1"
FILE_KEY_INFO = b"deployer-backups-v1 file"
KEY_MATERIAL_FORMAT = "deployer-backup-keys"

_extra_keys: dict[str, bytes] = {}
_extra_loaded = False
_lock = threading.Lock()


class BackupCryptoError(Exception):
    """Wrong key, corrupted or truncated artifact."""


def _hkdf(key: bytes, salt: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(key)


def derive_backup_key(master_key: bytes) -> bytes:
    return _hkdf(master_key, b"", BACKUP_KEY_INFO)


def backup_key() -> bytes:
    return derive_backup_key(_master_key())


def key_id(key: bytes) -> bytes:
    return hashlib.sha256(key).digest()[:8]


def _keys_file() -> Path:
    return Path(os.environ.get("BACKUP_DIR") or "/backups") / ".keys"


def _load_extra_keys() -> None:
    global _extra_loaded
    with _lock:
        if _extra_loaded:
            return
        _extra_loaded = True
        path = _keys_file()
        try:
            data = json.loads(decrypt_secret(path.read_text("utf-8").strip()))
        except (OSError, ValueError, InvalidTag):
            return
        for item in data.get("keys", []):
            raw = base64.b64decode(item["key"])
            _extra_keys[key_id(raw).hex()] = raw


def reset_key_cache() -> None:
    """Test hook: forget imported keys loaded from disk."""
    global _extra_loaded
    with _lock:
        _extra_keys.clear()
        _extra_loaded = False


def _key_for(kid: bytes) -> bytes:
    current = backup_key()
    if hmac.compare_digest(key_id(current), kid):
        return current
    _load_extra_keys()
    key = _extra_keys.get(kid.hex())
    if key is None:
        raise BackupCryptoError("This artifact was encrypted with an unknown backup key")
    return key


def _nonce(prefix: bytes, counter: int, last: bool) -> bytes:
    if counter >= 2**32:
        raise BackupCryptoError("Artifact too large")
    return prefix + counter.to_bytes(4, "big") + (b"\x01" if last else b"\x00")


class EncryptingWriter:
    """File-like sink: `write()` plaintext, `close()` seals the final chunk.

    Ciphertext goes to `dest`; `sha256` / `size` describe the ciphertext written so far.
    """

    def __init__(self, dest: IO[bytes], key: bytes | None = None):
        key = key or backup_key()
        salt, self._prefix = os.urandom(16), os.urandom(7)
        self._header = MAGIC + key_id(key) + salt + self._prefix
        self._aead = AESGCM(_hkdf(key, salt, FILE_KEY_INFO))
        self._dest = dest
        self._buf = bytearray()
        self._counter = 0
        self._closed = False
        self._hash = hashlib.sha256()
        self.size = 0
        self._emit(self._header)

    def _emit(self, data: bytes) -> None:
        self._dest.write(data)
        self._hash.update(data)
        self.size += len(data)

    def write(self, data: bytes) -> int:
        if self._closed:
            raise ValueError("write to closed EncryptingWriter")
        self._buf += data
        # Keep at least one byte buffered so the final chunk is never an unexpected empty one.
        while len(self._buf) > CHUNK_SIZE:
            chunk = bytes(self._buf[:CHUNK_SIZE])
            del self._buf[:CHUNK_SIZE]
            self._emit(self._aead.encrypt(_nonce(self._prefix, self._counter, False), chunk, self._header))
            self._counter += 1
        return len(data)

    def flush(self) -> None:
        self._dest.flush()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._emit(self._aead.encrypt(_nonce(self._prefix, self._counter, True), bytes(self._buf), self._header))
        self._buf.clear()
        self._dest.flush()

    @property
    def sha256(self) -> str:
        return self._hash.hexdigest()

    def __enter__(self) -> EncryptingWriter:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.close()


def iter_decrypt(src: IO[bytes]) -> Iterator[bytes]:
    """Yields plaintext chunks; raises BackupCryptoError on any tampering or truncation."""
    header = _read_exact(src, HEADER_SIZE)
    if len(header) != HEADER_SIZE or not header.startswith(MAGIC):
        raise BackupCryptoError("Not a Deployer backup artifact")
    kid, salt, prefix = header[6:14], header[14:30], header[30:37]
    aead = AESGCM(_hkdf(_key_for(kid), salt, FILE_KEY_INFO))
    counter = 0
    block = _read_exact(src, CHUNK_SIZE + TAG_SIZE)
    while True:
        if len(block) < TAG_SIZE:
            raise BackupCryptoError("Artifact is truncated")
        nxt = _read_exact(src, CHUNK_SIZE + TAG_SIZE) if len(block) == CHUNK_SIZE + TAG_SIZE else b""
        last = not nxt
        try:
            plain = aead.decrypt(_nonce(prefix, counter, last), block, header)
        except InvalidTag as exc:
            raise BackupCryptoError("Artifact failed authentication (wrong key, corrupted or truncated)") from exc
        if plain:
            yield plain
        if last:
            return
        counter += 1
        block = nxt


def _read_exact(src: IO[bytes], n: int) -> bytes:
    parts, remaining = [], n
    while remaining:
        chunk = src.read(remaining)
        if not chunk:
            break
        parts.append(chunk)
        remaining -= len(chunk)
    return b"".join(parts)


class DecryptingReader:
    """Read-only file-like object over `iter_decrypt` (for `shutil.copyfileobj`, gzip, subprocess feeding)."""

    def __init__(self, src: IO[bytes]):
        self._it = iter_decrypt(src)
        self._buf = b""
        self._eof = False

    def readable(self) -> bool:
        return True

    def read(self, n: int = -1) -> bytes:
        while not self._eof and (n < 0 or len(self._buf) < n):
            try:
                self._buf += next(self._it)
            except StopIteration:
                self._eof = True
        if n < 0:
            out, self._buf = self._buf, b""
        else:
            out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def readinto(self, b) -> int:  # pragma: no cover - used by some io consumers
        data = self.read(len(b))
        b[: len(data)] = data
        return len(data)

    def close(self) -> None:
        self._eof = True

    def __enter__(self) -> DecryptingReader:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Looked up on the instance so a wrapper that replaces `close` (open_artifact_plain) still runs.
        self.close()


def encrypt_stream(src: IO[bytes], dest: IO[bytes], key: bytes | None = None) -> dict[str, Any]:
    writer = EncryptingWriter(dest, key)
    while chunk := src.read(CHUNK_SIZE):
        writer.write(chunk)
    writer.close()
    return {"size_bytes": writer.size, "sha256": writer.sha256}


def decrypt_stream(src: IO[bytes], dest: IO[bytes]) -> int:
    total = 0
    for chunk in iter_decrypt(src):
        dest.write(chunk)
        total += len(chunk)
    return total


def sha256_file(path: str | os.PathLike) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------------------------
# key material for instance exports
# ---------------------------------------------------------------------------------------------


def export_key_material() -> dict[str, Any]:
    """Everything needed to decrypt this instance's backup artifacts elsewhere.

    Put the returned dict inside the (passphrase-encrypted) instance export payload, e.g. under
    `"backup_keys"`. It contains raw key bytes: never log it or store it unencrypted.
    """
    _load_extra_keys()
    keys = {key_id(backup_key()).hex(): backup_key(), **_extra_keys}
    return {
        "format": KEY_MATERIAL_FORMAT,
        "version": 1,
        "current_key_id": key_id(backup_key()).hex(),
        "keys": [{"id": kid, "key": base64.b64encode(raw).decode("ascii")} for kid, raw in keys.items()],
    }


def import_key_material(material: dict[str, Any] | None) -> int:
    """Adds backup keys from an export to this instance's key ring. Returns the number of new keys.

    Keys equal to the current MASTER_KEY-derived key are skipped. The key ring file lives in the
    backups volume, encrypted with the current MASTER_KEY.
    """
    if not material:
        return 0
    if material.get("format") != KEY_MATERIAL_FORMAT:
        raise ValueError("Unsupported backup key material")
    _load_extra_keys()
    current = key_id(backup_key()).hex()
    added = 0
    with _lock:
        for item in material.get("keys", []):
            raw = base64.b64decode(item["key"])
            if len(raw) != 32:
                raise ValueError("Invalid backup key length")
            kid = key_id(raw).hex()
            if kid == current or kid in _extra_keys:
                continue
            _extra_keys[kid] = raw
            added += 1
        if added:
            path = _keys_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"keys": [{"id": k, "key": base64.b64encode(v).decode("ascii")} for k, v in _extra_keys.items()]}
            tmp = path.with_suffix(".tmp")
            tmp.write_text(encrypt_secret(json.dumps(payload)), "utf-8")
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, path)
    return added
