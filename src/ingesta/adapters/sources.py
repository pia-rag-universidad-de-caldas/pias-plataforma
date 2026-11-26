"""The ingestion sources (feature 030): each kind opens as a read-only models.FileAdapter for the domain.

A folder is a LocalFileAdapter on it. An external SQL database will be another FileAdapter that lists its files and
hands their content (Organization only calls list_files, info and copy_from on the source); until then it is
SourceUnavailable.
"""

from ingesta.models import FileAdapter, SourceKind, SourceUnavailable

from .local_files import LocalFileAdapter, overlaps


def open_source(kind: SourceKind, location: str) -> FileAdapter:
    """The source as a FileAdapter; SourceUnavailable for the kinds that don't exist yet."""
    if kind is SourceKind.FOLDER:
        return LocalFileAdapter(location)
    raise SourceUnavailable(f"the {kind.value!r} source is not available yet: only {SourceKind.FOLDER.value!r} is")


def overlaps_ingest(kind: SourceKind, location: str, ingest: str) -> bool:
    """Whether a folder source is the ingesta folder, is inside it or contains it."""
    return kind is SourceKind.FOLDER and overlaps(location, ingest)
