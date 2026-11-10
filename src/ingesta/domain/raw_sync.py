"""RawSync (feature 042): publishes the chunkable files in data, one RAW per content, after each ingestion.

Every chunkable file data doesn't have yet is published, not only the new ones of the run: the first run publishes the
corpus that was already there, and a run with nothing new retries what couldn't be published. A RAW whose file stopped
being chunkable is marked as no longer current, never deleted. One file at a time: a big one doesn't drag the others.
"""

import math
from collections.abc import Mapping

from ingesta.models import (
    FileError,
    FileReader,
    FileRecord,
    RawFailure,
    RawFileRejected,
    RawPlan,
    RawPreview,
    RawStore,
    RawSummary,
)

MAX_RAW_FAILURES = 200  # failures listed in a summary (all of them count)
BATCH_OVERHEAD = 64 * 1024  # what the rest of a RAW batch takes besides the content (properties, JSON)


def encoded_size(size: int) -> int:
    """Bytes of the batch of a file of `size` bytes: its base64 plus the rest of the batch."""
    return 4 * math.ceil(size / 3) + BATCH_OVERHEAD


class RawSync:
    """Only static methods: plan and run."""

    @staticmethod
    def plan(records: list[FileRecord], chunkable: set[str], published: Mapping[str, bool]) -> RawPlan:
        """`chunkable`: the origins classified as apto_chunking. A content has at most one chunkable file (hash
        duplicates aren't chunkable); a file without a hash yet is left for a later run."""
        current: dict[str, FileRecord] = {}
        for record in records:
            if record.origen in chunkable and record.sha256:
                current.setdefault(record.sha256, record)
        upload = [record for sha256, record in sorted(current.items()) if not published.get(sha256, False)]
        retire = sorted(sha256 for sha256, vigente in published.items() if vigente and sha256 not in current)
        return RawPlan(upload, len(current) - len(upload), retire)

    @staticmethod
    def preview(plan: RawPlan) -> RawPreview:
        return RawPreview(subiria=len(plan.upload), ya_estan=plan.already, retiraria=len(plan.retire))

    @staticmethod
    def run(plan: RawPlan, store: RawStore, ingest: FileReader, limit: int, at: str) -> RawSummary:
        """Publishes `plan`. A file that doesn't fit in `limit` (data's max_body_bytes) or that data refuses fails
        alone; data down (RawStoreError) stops the publication and is raised to the caller."""
        failures: list[RawFailure] = []
        uploaded = 0
        for record in plan.upload:
            sha256 = record.sha256 or ""
            if encoded_size(record.bytes) > limit:
                error = f"{record.bytes} bytes don't fit in a batch of data (at most {limit} with its base64)"
                failures.append(RawFailure(sha256, record.origen, error))
                continue
            try:
                content = b"".join(ingest.read_chunks(record.destino))
                store.publish(record, content, at)
            except (FileError, RawFileRejected) as e:
                failures.append(RawFailure(sha256, record.origen, str(e)))
                continue
            uploaded += 1
        if plan.retire:
            store.retire(plan.retire)
        return RawSummary(
            subidos=uploaded,
            ya_estaban=plan.already,
            retirados=len(plan.retire),
            fallidos=len(failures),
            errores=failures[:MAX_RAW_FAILURES],
        )
