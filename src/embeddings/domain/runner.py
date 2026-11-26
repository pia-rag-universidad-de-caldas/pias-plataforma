"""Runner: production. Embeds the official chunks of the given chunked documents that changed for the run's model. A
bad document never stops it; only the outside does (UpstreamDown: data or the model down).

Each model has its own vector property and fingerprint (feature 055): a run with another model (`model` of the
request) embeds next to the active one without touching its vectors, so the chat keeps answering with the active one
until PUT /config makes the other active.

Each chunk is embedded with its course in front (feature 057, identity.py): the name and code read from the
document's header, which only its first chunks have, so that a question naming a course finds the rest of its PIAA
too. The JSON keeps the course (consultas filters by it) and the chunks the vectors were calculated over (data counts
what is missing with it). Without sha256s, a run takes what data says is missing when its turn comes. `events.stop`
(feature 056) is asked before each document: once it says so, the run ends there, keeping what it did."""

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

from .batches import document_batch, marked_batch
from .events import RunEvents, check_lengths, vectors
from .fingerprint import document_fingerprint
from .identity import HEADER_CHUNKS, identify, passage_heading
from .indexes import embedded_over_key, fingerprint_key, vector_index, vector_property

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
        if not sha256s:  # what is missing with that model, now that its turn came
            sha256s = source.missing(vector_property(config.model), request.page, request.per_page)
            events.listed(sha256s)
        progress = RunProgress(total=len(sha256s))
        if not request.simulate:
            sink.ensure_index(vector_index(GraphLabel.FRAGMENTOS, config.model))  # idempotent: before any vector
        for sha256 in sha256s:
            if events.stop():
                break
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
            identity = identify([c.text for c in chunks[:HEADER_CHUNKS]], document.file_name)
            heading = passage_heading(identity)
            fingerprint = document_fingerprint(model, chunks, heading)
            if fingerprint == document.fingerprints.get(fingerprint_key(model)) and not request.force:
                if not request.simulate and document.embedded_over.get(embedded_over_key(model)) != document.chunking:
                    sink.save(marked_batch(sha256, model, identity, document.chunking))  # embedded before 057
                events.embedded(sha256)
                return replace(progress, unchanged=progress.unchanged + 1)
            if request.simulate:
                check_lengths(embedder, model, limit, chunks)
            else:
                found = vectors(embedder, model, limit, chunks, heading)
                sink.save(document_batch(sha256, chunks, found, config, fingerprint, identity, document.chunking))
                events.embedded(sha256)
        except DocumentError as error:
            events.failure(DocumentFailure(sha256, str(error)))
            return replace(progress, errors=progress.errors + 1)
        return replace(progress, embedded=progress.embedded + 1, chunks=progress.chunks + len(chunks))
