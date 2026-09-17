"""Decrypted artifact streams are used in `with` blocks by the restore paths (the MongoDB restore opens
them uncompressed, so it gets the bare reader); both wrappers must be context managers that close the
underlying file."""

import builtins
import io

from app.services import backup_crypto as bc
from app.services import backup_engine


def _encrypted(payload: bytes) -> bytes:
    raw = io.BytesIO()
    bc.encrypt_stream(io.BytesIO(payload), raw)
    return raw.getvalue()


def test_decrypting_reader_is_a_context_manager():
    with bc.DecryptingReader(io.BytesIO(_encrypted(b"hello"))) as reader:
        assert reader.read() == b"hello"


def test_open_artifact_plain_uncompressed_closes_file_on_exit(tmp_path, monkeypatch):
    path = tmp_path / "artifact.bin"
    path.write_bytes(_encrypted(b"payload"))
    opened: list = []

    def recording_open(*args, **kwargs):
        fh = builtins.open(*args, **kwargs)
        opened.append(fh)
        return fh

    # Shadow the builtin inside the module so the raw file handle can be observed.
    monkeypatch.setattr(backup_engine, "open", recording_open, raising=False)

    with backup_engine.open_artifact_plain(path, compressed=False) as stream:
        assert stream.read() == b"payload"

    assert len(opened) == 1 and opened[0].closed
