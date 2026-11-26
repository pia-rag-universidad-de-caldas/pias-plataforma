"""Upload rules (feature 049): where an uploaded file goes in base/, under which name, and which ones are refused. The
upload only writes in base/ and records it: the next ingestion copies, classifies and publishes it."""

import hashlib
import re
import unicodedata
from collections.abc import Sequence
from datetime import datetime
from typing import ClassVar

from ingesta.config import CODE_DIGITS, MAX_NAME, MONTH_FOLDERS, WEEK_DAYS
from ingesta.models import (
    FileRepository,
    FileWriter,
    IncomingFile,
    MemoryStoreError,
    Upload,
    UploadRepository,
    UploadResult,
    UploadState,
)

from .discovery import Discovery
from .naming import Naming


class Uploads:
    """Only static methods: the upload rules under one name."""

    _UNSAFE: ClassVar[re.Pattern[str]] = re.compile(r'[<>:"|?*]')  # not valid in a Windows name
    _SPACES: ClassVar[re.Pattern[str]] = re.compile(r"\s+")

    @staticmethod
    def valid_code(code: str) -> bool:
        """Six digits; UNASSIGNED_CODE (000000) is one of them: a file without PIAA."""
        return len(code) == CODE_DIGITS and code.isascii() and code.isdigit()

    @staticmethod
    def folder(code: str, when: datetime) -> str:
        """<anio>/<mes>/<semana>/<codigo> of the upload date, named as the corpus names them:
        2026/11_Noviembre/Semana_02/023560."""
        week = (when.day - 1) // WEEK_DAYS + 1
        return f"{when.year}/{MONTH_FOLDERS[when.month - 1]}/Semana_{week:02d}/{code}"

    @staticmethod
    def clean_name(name: str) -> str:
        """The name without folders (whatever the client put before the last / or \\), without control characters
        or the ones Windows refuses, and with spaces as "_", as in the corpus."""
        name = unicodedata.normalize("NFC", re.split(r"[/\\]", name)[-1])
        name = "".join(c for c in name if unicodedata.category(c)[0] != "C")
        return Uploads._SPACES.sub("_", Uploads._UNSAFE.sub("_", name).strip())

    @staticmethod
    def stored_name(name: str, when: datetime) -> str:
        """The clean name behind the prefix the upload system puts on the corpus names (2025-01-28-16.16.41.000000_),
        which Repetitions already strips to compare names."""
        return f"{when:%Y-%m-%d-%H.%M.%S.%f}_{name}"

    @staticmethod
    def problem(name: str, size: int) -> str | None:
        """Why a file is refused, given its clean name; None if it can be saved."""
        if not name or name in (".", "..") or Discovery.is_hidden(name):
            return "nombre vacío u oculto"
        if len(name.encode()) > MAX_NAME:
            return f"nombre de más de {MAX_NAME} bytes"
        file_type = Naming.file_type(name)
        if not Naming.is_supported(file_type):
            return f"tipo {file_type} no admitido: solo pdf, doc y docx"
        if Naming.is_empty(size):
            return "archivo vacío o casi vacío: no tendría qué fragmentar"
        return None

    @staticmethod
    def existing(sha256: str, files: FileRepository, uploads: UploadRepository) -> str | None:
        """Where that content already is in base/ (ingested or only uploaded); None if it is new."""
        known = [r.origen for r in files.with_hash(sha256)] or [u.origen for u in uploads.with_hash(sha256)]
        return known[0] if known else None

    @staticmethod
    def save(
        base: FileWriter,
        files: FileRepository,
        uploads: UploadRepository,
        code: str,
        incoming: Sequence[IncomingFile],
        when: datetime,
    ) -> list[UploadResult]:
        """Saves each file in base/ and records it, in order (two equal files in one upload: the second one already
        exists). Never overwrites. A disk failure (FileError) or a memory failure (MemoryStoreError) stops the upload:
        what was saved before stays saved and recorded, and a file written but not recorded is deleted."""
        folder = Uploads.folder(code, when)
        results: list[UploadResult] = []
        for file in incoming:
            sha256 = hashlib.sha256(file.content).hexdigest()
            name = Uploads.clean_name(file.name)
            if reason := Uploads.problem(name, len(file.content)):
                results.append(UploadResult(file.name, UploadState.REJECTED, sha256, motivo=reason))
                continue
            if path := Uploads.existing(sha256, files, uploads):
                results.append(UploadResult(file.name, UploadState.EXISTS, sha256, ruta=path))
                continue
            base.make_dir(folder)
            target = base.free_name(folder, Uploads.stored_name(name, when))
            base.write_new(target, (file.content,))
            try:
                uploads.insert(Upload(target, file.name, code, sha256, len(file.content), when.isoformat()))
            except MemoryStoreError:
                base.delete(target, missing_ok=True)
                raise
            results.append(UploadResult(file.name, UploadState.SAVED, sha256, ruta=target))
        return results
