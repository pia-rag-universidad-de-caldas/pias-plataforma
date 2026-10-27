"""Selection: which documents of a page still have to be chunked."""

from collections.abc import Mapping

from chunking.models import DocumentStatus, ProcessedDocument, SourceDocument


class Selection:
    @staticmethod
    def is_pending(
        document: SourceDocument, processed: ProcessedDocument | None, fingerprint: str, retry_errors: bool
    ) -> bool:
        """New, with another content (sha256), chunked with other parameters (fingerprint), or in error and
        `retry_errors`. A document in error with other parameters is retried anyway: they may fix it."""
        if processed is None or processed.sha256 != document.sha256 or processed.fingerprint != fingerprint:
            return True
        return retry_errors and processed.status == DocumentStatus.ERROR

    @staticmethod
    def pending(
        page: list[SourceDocument],
        processed: Mapping[str, ProcessedDocument],
        fingerprint: str,
        retry_errors: bool,
    ) -> list[SourceDocument]:
        """The pending documents of one page, in its order (`processed` is by origin, as ChunkSink gives it)."""
        return [d for d in page if Selection.is_pending(d, processed.get(d.origin), fingerprint, retry_errors)]
