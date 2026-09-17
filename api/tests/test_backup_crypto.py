"""Chunked AES-256-GCM STREAM encryption of backup artifacts (app.services.backup_crypto)."""

import base64
import gzip
import io
import os

import pytest

from app.config import get_settings
from app.services import backup_crypto as bc


@pytest.fixture(autouse=True)
def _backup_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    bc.reset_key_cache()
    yield
    bc.reset_key_cache()


def _encrypt(data: bytes, key: bytes | None = None) -> tuple[bytes, dict]:
    out = io.BytesIO()
    info = bc.encrypt_stream(io.BytesIO(data), out, key)
    return out.getvalue(), info


def _decrypt(blob: bytes) -> bytes:
    out = io.BytesIO()
    bc.decrypt_stream(io.BytesIO(blob), out)
    return out.getvalue()


@pytest.mark.parametrize("size", [0, 1, bc.CHUNK_SIZE - 1, bc.CHUNK_SIZE, bc.CHUNK_SIZE + 1, 3 * bc.CHUNK_SIZE + 17])
def test_roundtrip_sizes(size):
    data = os.urandom(size)
    blob, info = _encrypt(data)
    assert blob.startswith(bc.MAGIC)
    assert info["size_bytes"] == len(blob)
    import hashlib

    assert info["sha256"] == hashlib.sha256(blob).hexdigest()
    chunks = max(1, -(-size // bc.CHUNK_SIZE))
    assert len(blob) == bc.HEADER_SIZE + size + chunks * bc.TAG_SIZE
    assert _decrypt(blob) == data


def test_small_writes_and_reader_with_gzip():
    raw = io.BytesIO()
    writer = bc.EncryptingWriter(raw)
    with gzip.GzipFile(fileobj=writer, mode="wb") as gz:
        for i in range(5000):
            gz.write(f"INSERT INTO t VALUES ({i});\n".encode())
    writer.close()
    reader = bc.DecryptingReader(io.BytesIO(raw.getvalue()))
    lines = gzip.GzipFile(fileobj=reader, mode="rb").read().splitlines()
    assert len(lines) == 5000 and lines[-1] == b"INSERT INTO t VALUES (4999);"


def test_same_plaintext_encrypts_differently():
    a, _ = _encrypt(b"hello")
    b, _ = _encrypt(b"hello")
    assert a != b and _decrypt(a) == _decrypt(b) == b"hello"


def _two_chunk_blob() -> bytes:
    return _encrypt(os.urandom(bc.CHUNK_SIZE + 100))[0]


def test_tampering_detected():
    blob = bytearray(_two_chunk_blob())
    blob[bc.HEADER_SIZE + 10] ^= 1
    with pytest.raises(bc.BackupCryptoError):
        _decrypt(bytes(blob))


def test_header_tampering_detected():
    blob = bytearray(_two_chunk_blob())
    blob[30] ^= 1  # nonce prefix
    with pytest.raises(bc.BackupCryptoError):
        _decrypt(bytes(blob))


def test_truncation_at_chunk_boundary_detected():
    blob = _two_chunk_blob()
    first_chunk_end = bc.HEADER_SIZE + bc.CHUNK_SIZE + bc.TAG_SIZE
    with pytest.raises(bc.BackupCryptoError):
        _decrypt(blob[:first_chunk_end])  # drops the (last) second chunk
    with pytest.raises(bc.BackupCryptoError):
        _decrypt(blob[:-5])


def test_chunk_reordering_detected():
    data = os.urandom(3 * bc.CHUNK_SIZE)
    blob = _encrypt(data)[0]
    n = bc.CHUNK_SIZE + bc.TAG_SIZE
    h = bc.HEADER_SIZE
    swapped = blob[:h] + blob[h + n : h + 2 * n] + blob[h : h + n] + blob[h + 2 * n :]
    with pytest.raises(bc.BackupCryptoError):
        _decrypt(swapped)


def test_not_an_artifact():
    with pytest.raises(bc.BackupCryptoError):
        _decrypt(b"plain text file")


def test_key_is_derived_from_master_key():
    master = base64.b64decode(get_settings().master_key)
    assert bc.backup_key() == bc.derive_backup_key(master)
    assert bc.backup_key() != master


def test_key_material_export_import(monkeypatch):
    old_blob = _encrypt(b"old instance data")[0]
    material = bc.export_key_material()
    assert material["format"] == "deployer-backup-keys" and len(material["keys"]) == 1
    assert base64.b64decode(material["keys"][0]["key"]) == bc.backup_key()

    # A restored instance with a different MASTER_KEY can't read the artifact until the keys are imported.
    settings = get_settings()
    monkeypatch.setattr(settings, "master_key", base64.b64encode(os.urandom(32)).decode())
    bc.reset_key_cache()
    with pytest.raises(bc.BackupCryptoError):
        _decrypt(old_blob)
    assert bc.import_key_material(material) == 1
    assert bc.import_key_material(material) == 0  # idempotent
    assert _decrypt(old_blob) == b"old instance data"

    # The key ring persists (encrypted with the new MASTER_KEY) and is exported again.
    bc.reset_key_cache()
    assert _decrypt(old_blob) == b"old instance data"
    assert len(bc.export_key_material()["keys"]) == 2
    ring = (bc._keys_file()).read_text()
    assert material["keys"][0]["key"] not in ring


def test_import_rejects_garbage():
    with pytest.raises(ValueError):
        bc.import_key_material({"format": "nope"})
    assert bc.import_key_material(None) == 0
