"""File tools that don't touch the disk (the FileAdapter does that)."""

import mimetypes
from datetime import datetime

from ingesta.models import FileInfo, FileMetadata


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).isoformat(timespec="seconds")


def read_metadata(info: FileInfo, name: str) -> FileMetadata:
    """Metadata for the memory. The creation date only exists on some systems (not on Linux)."""
    return FileMetadata(
        modified=_iso(info.modified),
        created=_iso(info.created) if info.created is not None else None,
        changed=_iso(info.changed),
        accessed=_iso(info.accessed),
        permissions=info.permissions,
        mime=mimetypes.guess_type(name, strict=False)[0],
    )
