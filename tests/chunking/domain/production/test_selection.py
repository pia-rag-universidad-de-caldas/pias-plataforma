"""Selection (feature 023): which documents of a page are still pending."""

import pytest

from chunking.domain import Selection
from chunking.models import (
    DocumentStatus,
    ProcessedDocument,
    SourceDocument,
)

DOC = SourceDocument("2024/a.pdf", "v/a.pdf", "a.pdf", "h1", "pdf", 2024, "020055")


def done(
    sha256: str = "h1", fingerprint: str = "f1", status: DocumentStatus = DocumentStatus.CHUNKED
) -> ProcessedDocument:
    return ProcessedDocument(DOC.origin, sha256, fingerprint, status)


@pytest.mark.parametrize(
    ("processed", "retry", "pending"),
    [
        (None, False, True),  # new
        (done(), False, False),  # same content and parameters
        (done(sha256="h0"), False, True),  # the origin has another content now
        (done(fingerprint="f0"), False, True),  # chunked with other parameters
        (done(status=DocumentStatus.ERROR), False, False),  # failed with these parameters: only with retry_errors
        (done(status=DocumentStatus.ERROR), True, True),
        (done(fingerprint="f0", status=DocumentStatus.ERROR), False, True),  # other parameters may fix it
    ],
)
def test_pending(processed: ProcessedDocument | None, retry: bool, pending: bool) -> None:
    assert Selection.is_pending(DOC, processed, "f1", retry) is pending


def test_pending_keeps_the_page_order() -> None:
    other = SourceDocument("2024/b.pdf", "v/b.pdf", "b.pdf", "h2", "pdf", 2024, None)
    assert Selection.pending([other, DOC], {DOC.origin: done()}, "f1", False) == [other]
