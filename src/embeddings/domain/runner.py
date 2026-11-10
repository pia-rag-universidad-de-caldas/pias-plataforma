"""Runner: production. Embeds the official chunks of the given chunked documents that changed for the run's model. A
bad document never stops it; only the outside does (UpstreamDown: data or the model down).

Each model has its own vector property and fingerprint (feature 055): a run with another model (`model` of the
request) embeds next to the active one without touching its vectors, so the chat keeps answering with the active one
until PUT /config makes the other active."""

from dataclasses import replace

from embeddings.models import (
    ChunkSource,
    DocumentError,
    DocumentFailure,
    Embedder,
    EmbeddingConfig,
    GraphLabel,
    RunProgress,
    RunRequest,
    VectorSink,
)

from .batches import document_batch
from .events import RunEvents, check_lengths, vectors
from .fingerprint import document_fingerprint
from .indexes import fingerprint_key, vector_index

NO_JSON = "no JSON in data with that sha256"


class Runner:
    @staticmethod
    def run(
        source: ChunkSource,
        sink: VectorSink,
        embedder: Embedder,
        config: EmbeddingConfig,
        request: RunRequest,
        events: RunEvents | None = None,
    ) -> RunProgress:
        """`config` is already resolved (the active one when the run was queued, or the model asked for: see
        run_config). UpstreamDown goes through: whoever runs it marks the run as failed. With `simulate`, everything
        is checked (the lengths too) but nothing is calculated nor written."""
        events = events or RunEvents()
        sha256s = list(dict.fromkeys(request.sha256s))
        progress = RunProgress(total=len(sha256s))
        if not request.simulate:
            sink.ensure_index(vector_index(GraphLabel.FRAGMENTOS, config.model))  # idempotent: before any vector
        for sha256 in sha256s:
            progress = Runner._document(source, sink, embedder, config, request, sha256, progress, events)
            events.progress(progress)
        return progress

    @staticmethod
    def _document(
        source: ChunkSource,
        sink: VectorSink,
        embedder: Embedder,
        config: EmbeddingConfig,
        request: RunRequest,
        sha256: str,
        progress: RunProgress,
        events: RunEvents,
    ) -> RunProgress:
        model, limit = config.model, config.max_tokens
        document = source.document(sha256)
        if document is None:  # asked for, but not in data
            events.failure(DocumentFailure(sha256, NO_JSON))
            return replace(progress, missing=progress.missing + 1)
        if not document.chunked:  # not chunked yet, or in error: it waits for chunking
            return replace(progress, skipped=progress.skipped + 1)
        try:
            chunks = source.chunks(sha256)
            fingerprint = document_fingerprint(model, chunks)
            if fingerprint == document.fingerprints.get(fingerprint_key(model)) and not request.force:
                events.embedded(sha256)
                return replace(progress, unchanged=progress.unchanged + 1)
            if request.simulate:
                check_lengths(embedder, model, limit, chunks)
            else:
                found = vectors(embedder, model, limit, chunks)
                sink.save(document_batch(sha256, chunks, found, config, fingerprint))
                events.embedded(sha256)
        except DocumentError as error:
            events.failure(DocumentFailure(sha256, str(error)))
            return replace(progress, errors=progress.errors + 1)
        return replace(progress, embedded=progress.embedded + 1, chunks=progress.chunks + len(chunks))
