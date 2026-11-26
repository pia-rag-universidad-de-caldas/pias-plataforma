"""ExperimentRunner: the laboratory. Embeds the EXP_CHUNK of a finished chunking experiment with the model and limit
it tries, one EXP_EMBED per chunk (feature 055: several experiments over the same chunks coexist); never touches the
official JSON nor compares fingerprints (each experiment is calculated whole)."""

from collections.abc import Sequence
from dataclasses import replace

from common.clock import now
from embeddings.config import EMBEDDABLE_EXPERIMENTS
from embeddings.models import (
    ChunkSource,
    ConfigOrigin,
    ConfigStore,
    DocumentError,
    DocumentFailure,
    Embedder,
    EmbeddingConfig,
    ExperimentRequest,
    GraphBatch,
    GraphLabel,
    RunProgress,
    VectorSink,
)

from .batches import cleared_batch, experiment_batch
from .events import RunEvents, check_lengths, vectors
from .indexes import vector_index
from .limits import token_limit


class UnknownExperiment(LookupError):
    """There is no chunking experiment with that id: 404."""


class UnfinishedExperiment(Exception):
    """The chunking experiment didn't end well (it waits, runs, failed or was interrupted): 409."""


class ExperimentRunner:
    @staticmethod
    def config(request: ExperimentRequest, id: str) -> EmbeddingConfig:
        """What experiment `id` tries; InvalidLimit (422) before anything runs."""
        limit = token_limit(request.model, request.max_tokens)
        return EmbeddingConfig(request.model, limit, ConfigOrigin.EXPERIMENT, id)

    @staticmethod
    def check(source: ChunkSource, chunking_experiment: str) -> None:
        """UnknownExperiment or UnfinishedExperiment: its chunks are only taken once it ended, finished or partial
        (feature 059: in one of the whole corpus a single failed document makes it partial; what it chunked is
        embedded)."""
        status = source.experiment_status(chunking_experiment)
        if status is None:
            raise UnknownExperiment(f"there is no chunking experiment {chunking_experiment!r}")
        if status not in EMBEDDABLE_EXPERIMENTS:
            raise UnfinishedExperiment(
                f"the chunking experiment {chunking_experiment!r} is {status}, not finished nor partial"
            )

    @staticmethod
    def run(
        source: ChunkSource,
        sink: VectorSink,
        embedder: Embedder,
        config: EmbeddingConfig,
        chunking_experiment: str,
        simulate: bool = False,
        events: RunEvents | None = None,
        documents: list[str] | None = None,
        start: RunProgress | None = None,
    ) -> RunProgress:
        """UpstreamDown goes through; a document that fails, only that document. One document at a time (feature 059:
        only the ids of all of them are in memory); one without chunks (it failed in chunking) is skipped. On a resume
        (feature 062), `documents` are only those still missing and `start` the progress it already had."""
        events = events or RunEvents()
        if documents is None:
            documents = source.experiment_documents(chunking_experiment)
        progress = start or RunProgress(total=len(documents))
        if not simulate:
            sink.ensure_index(vector_index(GraphLabel.EXP_EMBED, config.model))
        for sha256 in documents:
            chunks = source.experiment_document_chunks(chunking_experiment, sha256)
            if not chunks:
                progress = replace(progress, skipped=progress.skipped + 1)
                events.progress(progress)
                continue
            try:
                if simulate:
                    check_lengths(embedder, config.model, config.max_tokens, chunks)
                else:
                    found = vectors(embedder, config.model, config.max_tokens, chunks)
                    sink.save(experiment_batch(chunks, found, config))
                    events.embedded(sha256)
                progress = replace(progress, embedded=progress.embedded + 1, chunks=progress.chunks + len(chunks))
            except DocumentError as error:
                events.failure(DocumentFailure(sha256, str(error)))
                progress = replace(progress, errors=progress.errors + 1)
            events.progress(progress)
        return progress

    @staticmethod
    def pending(source: ChunkSource, id: str, chunking_experiment: str, only: Sequence[str] = ()) -> list[str]:
        """What a resume of experiment `id` embeds (feature 062): the chunked documents of its chunking experiment
        without its vectors (all of them, if data doesn't know `id` yet); with `only`, just those of them."""
        missing = source.experiment_missing(id)
        if missing is None:
            missing = source.experiment_documents(chunking_experiment)
        if not only:
            return missing
        asked = set(only)
        return [sha256 for sha256 in missing if sha256 in asked]

    @staticmethod
    def cleared(id: str) -> GraphBatch:
        """What deleting experiment `id` removes first: its EXP_EMBED (replace_from its EXP_EMBEDDINGS), never the
        chunks nor another experiment's vectors (feature 055). Then its record goes."""
        return cleared_batch(id)

    @staticmethod
    def apply(store: ConfigStore, config: EmbeddingConfig) -> EmbeddingConfig:
        """The experiment's model and limit become the active configuration. Nothing is processed."""
        active = replace(config, origin=ConfigOrigin.EXPERIMENT, modified=now())
        store.set(active)
        return active
