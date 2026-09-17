"""`device_rpc.move_file` must work across filesystems: in the container the transfer store lives on the
`/backups` volume while temp files live in `/tmp`, and a plain rename between them fails with EXDEV."""

import errno
import os

import pytest

from app.services import device_rpc


def test_move_file_falls_back_to_copy_on_cross_device_rename(tmp_path, monkeypatch):
    src = tmp_path / "src.bin"
    dst = tmp_path / "dst.bin"
    src.write_bytes(b"payload")
    dst.write_bytes(b"stale")

    real_replace = os.replace

    def exdev(a, b, *args, **kwargs):
        raise OSError(errno.EXDEV, "Invalid cross-device link", str(a), None, str(b))

    monkeypatch.setattr(os, "replace", exdev)
    device_rpc.move_file(src, dst)
    monkeypatch.setattr(os, "replace", real_replace)

    assert dst.read_bytes() == b"payload"
    assert not src.exists()


def test_move_file_reraises_other_errors(tmp_path, monkeypatch):
    def denied(a, b, *args, **kwargs):
        raise PermissionError(errno.EACCES, "denied")

    monkeypatch.setattr(os, "replace", denied)
    with pytest.raises(PermissionError):
        device_rpc.move_file(tmp_path / "a", tmp_path / "b")
