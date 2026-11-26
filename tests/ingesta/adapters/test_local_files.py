"""LocalFileAdapter.write_new (feature 049): atomic, hidden while it writes, never overwrites."""

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from ingesta.adapters import LocalFileAdapter
from ingesta.models import FileError


def test_it_writes_the_blocks_and_returns_their_sha256(tmp_path: Path) -> None:
    sha = LocalFileAdapter(str(tmp_path)).write_new("a.pdf", [b"ab", b"cd"])
    assert (tmp_path / "a.pdf").read_bytes() == b"abcd" and sha == hashlib.sha256(b"abcd").hexdigest()


def test_an_existing_file_is_never_overwritten(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"old")
    with pytest.raises(FileError):
        LocalFileAdapter(str(tmp_path)).write_new("a.pdf", [b"new"])
    assert (tmp_path / "a.pdf").read_bytes() == b"old" and sorted(p.name for p in tmp_path.iterdir()) == ["a.pdf"]


def test_a_writer_does_not_remove_another_uploads_partial_file(tmp_path: Path) -> None:
    partial = tmp_path / ".a.pdf.parcial"
    partial.write_bytes(b"owned by another upload")
    with pytest.raises(FileError):
        LocalFileAdapter(str(tmp_path)).write_new("a.pdf", [b"new"])
    assert partial.read_bytes() == b"owned by another upload"


def test_while_it_writes_only_a_hidden_name_exists(tmp_path: Path) -> None:
    seen: list[str] = []

    def blocks() -> Iterator[bytes]:
        seen.extend(p.name for p in tmp_path.iterdir())
        yield b"x"
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        LocalFileAdapter(str(tmp_path)).write_new("a.pdf", blocks())
    assert seen == [".a.pdf.parcial"] and not list(tmp_path.iterdir())
