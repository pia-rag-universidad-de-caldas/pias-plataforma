"""IngestaHttpSource (ChunkSource, features 022 and 026): the chunkable files, asked to ingesta over HTTP through
IngestaFilesClient; ingesta's JSON becomes SourceDocument in ingesta/mappers.py."""

import hashlib
from collections.abc import Iterator

import httpx

from chunking.models import DocumentError, DocumentFilter, SourceDocument, SourceError

from .files_client import IngestaFilesClient
from .mappers import document


class IngestaHttpSource:
    def __init__(self, client: httpx.Client, path: str) -> None:
        self._files = IngestaFilesClient(client, path)

    def pages(
        self, filter: DocumentFilter, per_page: int, first: int = 1, last: int | None = None
    ) -> Iterator[list[SourceDocument]]:
        """Page after page of GET /data (from `first` to `last`, or to the end), each asked only when the previous one
        was consumed. The number of pages is the one of the first answer; if `reorganizado` changes in between
        (ingesta reorganized during the run), the pages may have shifted: SourceError."""
        reorganized = None
        for page, body in enumerate(self._files.pages(filter, per_page, first, last), start=first):
            try:
                rows, current = body["archivos"], body["reorganizado"]
            except KeyError as e:
                raise SourceError(f"ingesta answered a page without {e}") from e
            if page == first:
                reorganized = current
            if current != reorganized:
                raise SourceError(
                    f"ingesta was reorganized during the run ({reorganized} → {current}): its pages may have "
                    f"shifted, so the run stops after page {page - 1}; start it again"
                )
            yield [document(row) for row in rows]

    def find(self, sha256: str) -> SourceDocument:
        return document(self._files.file(sha256))

    def content(self, document: SourceDocument) -> bytes:
        """The bytes, checked against the sha256 ingesta has (a copy that changed is a failure of the document)."""
        content = self._files.content(document.origin)
        if document.sha256 and hashlib.sha256(content).hexdigest() != document.sha256:
            raise DocumentError(f"the content ingesta served doesn't have the sha256 it registered ({document.sha256})")
        return content
