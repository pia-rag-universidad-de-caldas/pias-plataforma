"""FileAdapter on the local disk.

The only file that uses pathlib, shutil, os and stat (Ruff bans them outside adapters/ with TID251). Each adapter
works under a root and receives paths relative to it, as text with "/".
"""

import hashlib
import os
import shutil
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from ingesta.config import PARTIAL_SUFFIX
from ingesta.models import FileAdapter, FileError, FileInfo, FileReader

# Project root: src/ingesta/adapters/local_files.py -> 3 levels up. Valid because uv installs the project in
# editable mode; otherwise, use --base/--ingest/--memory/--output.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def project_path(relative: str) -> str:
    """Full path of something inside the project (the config/ defaults)."""
    return str(_PROJECT_ROOT / relative)


def absolute_path(path: str) -> str:
    """Full path of what the user typed (relative to the current folder)."""
    return str(Path(path).resolve())


def overlaps(a: str, b: str) -> bool:
    """Whether two folders are the same or one is inside the other (an ingestion must not copy into its source)."""
    first, second = Path(a).resolve(), Path(b).resolve()
    return first == second or first.is_relative_to(second) or second.is_relative_to(first)


def folder_and_name(path: str) -> tuple["LocalFileAdapter", str]:
    """An adapter on the folder of `path` and the file name, to write or create a file (the SQLite memory)."""
    full = Path(path).resolve()
    return LocalFileAdapter(str(full.parent)), full.name


class LocalFileAdapter(FileAdapter):
    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()

    def _path(self, path: str) -> Path:
        if Path(path).is_absolute():
            raise ValueError(f"expected a path relative to {self._root}: {path}")
        return self._root / path

    # --- queries ---

    def absolute(self, path: str = "") -> str:
        return str(self._path(path))

    def exists(self, path: str = "") -> bool:
        return self._path(path).exists()

    def is_file(self, path: str) -> bool:
        return self._path(path).is_file()

    def is_dir(self, path: str = "") -> bool:
        return self._path(path).is_dir()

    def list_files(self) -> list[FileInfo]:
        found = []
        try:
            for path in self._root.rglob("*"):
                try:
                    st = path.stat()
                except OSError:  # it disappeared or can't be read: skipped
                    continue
                if stat.S_ISREG(st.st_mode):
                    found.append(self._info(path, st))
        except OSError as e:  # a folder that can't be listed (permissions...)
            raise FileError(str(e)) from e
        return found

    def info(self, path: str) -> FileInfo:
        full = self._path(path)
        try:
            return self._info(full, full.stat())
        except OSError as e:
            raise FileError(str(e)) from e

    def _info(self, path: Path, st: os.stat_result) -> FileInfo:
        return FileInfo(
            path=path.relative_to(self._root).as_posix(),
            bytes=st.st_size,
            modified=st.st_mtime,
            created=getattr(st, "st_birthtime", None),  # only exists on some systems (not on Linux)
            changed=st.st_ctime,
            accessed=st.st_atime,
            permissions=f"{stat.S_IMODE(st.st_mode):o}",
        )

    def hash(self, path: str) -> str:
        try:
            return self._hash(self._path(path))
        except OSError as e:
            raise FileError(str(e)) from e

    @staticmethod
    def _hash(path: Path) -> str:
        with path.open("rb") as f:
            return hashlib.file_digest(f, "sha256").hexdigest()

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        try:
            return self._path(path).read_text(encoding=encoding)
        except OSError as e:
            raise FileError(str(e)) from e

    def read_chunks(self, path: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        full = (self._root / path).resolve()
        if not full.is_relative_to(self._root):  # absolute, "..", or a link pointing outside the root
            raise FileError(f"{path} falls outside {self._root}")
        try:
            file = full.open("rb")  # now, not on the first next(): the error comes before streaming anything
        except OSError as e:
            raise FileError(str(e)) from e
        return self._chunks(file, chunk_size)

    @staticmethod
    def _chunks(file: BinaryIO, chunk_size: int) -> Iterator[bytes]:
        with file:
            try:
                while block := file.read(chunk_size):
                    yield block
            except OSError as e:
                raise FileError(str(e)) from e

    # --- changes ---

    def write_text(self, path: str, text: str, encoding: str = "utf-8") -> None:
        full = self._path(path)
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(text, encoding=encoding, newline="")
        except OSError as e:
            raise FileError(str(e)) from e

    def write_bytes(self, path: str, data: bytes) -> None:
        full = self._path(path)
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_bytes(data)
        except OSError as e:
            raise FileError(str(e)) from e

    def make_dir(self, path: str = "") -> None:
        try:
            self._path(path).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise FileError(str(e)) from e

    def free_name(self, folder: str, name: str) -> str:
        target = self._path(folder) / name
        if target.exists():
            stem, suffix = Path(name).stem, Path(name).suffix
            n = 1
            while (target := self._path(folder) / f"{stem}__{n}{suffix}").exists():
                n += 1
        return target.relative_to(self._root).as_posix()

    def copy_from(self, source: FileReader, path: str, target: str) -> str:
        final = self._path(target)
        partial = final.with_name(final.name + PARTIAL_SUFFIX)
        try:
            if isinstance(source, LocalFileAdapter):
                shutil.copy2(source._path(path), partial)  # keeps dates and permissions
                sha = self._hash(partial)
            else:  # any other source (an external database, feature 030): its content, block by block
                digest = hashlib.sha256()
                with partial.open("wb") as out:
                    for block in source.read_chunks(path):
                        digest.update(block)
                        out.write(block)
                sha = digest.hexdigest()
            partial.replace(final)
            return sha
        except BaseException as e:
            partial.unlink(missing_ok=True)
            if isinstance(e, OSError):
                raise FileError(str(e)) from e
            raise

    def move(self, path: str, target: str) -> None:
        try:
            self._path(path).replace(self._path(target))
        except OSError as e:
            raise FileError(str(e)) from e

    def delete(self, path: str, missing_ok: bool = False) -> None:
        try:
            self._path(path).unlink(missing_ok=missing_ok)
        except OSError as e:
            raise FileError(str(e)) from e

    def remove_empty_dirs(self, folder: str) -> None:
        current = self._path(folder)
        while current != self._root and current.is_relative_to(self._root):
            try:
                current.rmdir()
            except OSError:  # not empty or no longer exists
                return
            current = current.parent
