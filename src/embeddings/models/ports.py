"""What the domain asks of the outside, and the errors of each side. Everything is implemented over data (adapters/),
except the Embedder, the local models."""

from typing import Protocol

from .batch import GraphBatch
from .concepts import EmbeddableChunk, EmbeddableDocument, EmbeddingConfig, VectorIndexSpec
from .results import RunKind


class UpstreamDown(Exception):
    """data doesn't answer, or the model can't be loaded: it stops the run; nothing more is written."""


class DocumentError(Exception):
    """Only this document fails (a chunk over the limit, data refused its vectors): the others go on."""


class InvalidLimit(Exception):
    """A model that isn't served, or a token limit it doesn't admit: 422, nothing runs."""


class ChunkSource(Protocol):
    """The chunks as chunking left them in data."""

    def document(self, sha256: str) -> EmbeddableDocument | None:
        """The official JSON; None if data has none with that sha256."""
        ...

    def chunks(self, sha256: str) -> list[EmbeddableChunk]:
        """FRAGMENTOS under JSON → SECCION, by section order and index."""
        ...

    def missing(self, property: str, page: int | None, per_page: int | None) -> list[str]:
        """The chunked documents without that vector property's vectors over their current chunks, ordered by
        sha256 (GET /data/progress/embeddings): one page of them, or (page None) all."""
        ...

    def experiment_status(self, experiment: str) -> str | None:
        """The estado of a chunking EXPERIMENTO; None if there is none with that id."""
        ...

    def experiment_documents(self, experiment: str) -> list[str]:
        """The sha256s of the documents of a chunking experiment (its EXP_DOCUMENTO), ordered; empty if it has none.
        Only the ids (feature 059: one of the whole corpus has thousands): their chunks are read one at a time."""
        ...

    def experiment_missing(self, embeddings_experiment: str) -> list[str] | None:
        """Feature 062: the chunked documents of the chunking experiment an embeddings experiment embeds that don't
        have its vectors yet (GET /data/progress/experiment-embeddings), ordered; None if data doesn't know it."""
        ...

    def experiment_document_chunks(self, experiment: str, sha256: str) -> list[EmbeddableChunk]:
        """EXP_CHUNK under that EXP_DOCUMENTO → EXP_SECCION, by section order and index; empty if it has none (the
        document failed in chunking)."""
        ...

    def fingerprint_counts(self) -> dict[str, int]:
        """How many official JSON have each fingerprint key (huella_embedding_<model>_<dim>): a model's documents."""
        ...

    def with_fingerprint(self, key: str) -> list[str]:
        """The sha256s of the official JSON that have that fingerprint key."""
        ...


class VectorSink(Protocol):
    def ensure_index(self, index: VectorIndexSpec) -> None:
        """Creates it if missing; UpstreamDown if one with that name exists with another definition."""
        ...

    def save(self, batch: GraphBatch) -> None:
        """All of it or nothing; DocumentError if data refuses it."""
        ...

    def drop_index(self, name: str, drop_property: bool) -> bool:
        """Drops the index (and, with drop_property, its property from its nodes); False if there was none."""
        ...


class ConfigStore(Protocol):
    def active(self) -> EmbeddingConfig | None:
        """The stored one, as it is (domain/active_config.py decides if it still works); None if none."""
        ...

    def set(self, config: EmbeddingConfig) -> None: ...

    def clear(self) -> bool:
        """False if there was none."""
        ...


class RunStore(Protocol):
    """The record of the runs and experiments (CORRIDA_EMBEDDINGS, EXP_EMBEDDINGS): each one as the JSON GET answers
    (api/history.py turns it into an EmbeddingRun and back)."""

    def save(self, kind: RunKind, id: str, status: str, requested: str, detail: str) -> None: ...

    def link(self, id: str, chunking_experiment: str) -> None:
        """An experiment's link to the chunking experiment whose chunks it embeds (EXP_USA)."""
        ...

    def linked_by(self, id: str) -> list[str]:
        """The pipeline iterations that link the experiment (PIPE_USA, feature 055 part b); [] if there is none."""
        ...

    def details(self, kind: RunKind) -> list[str]:
        """Every stored one of that kind, as its JSON."""
        ...

    def detail(self, kind: RunKind, id: str) -> str | None: ...

    def delete(self, kind: RunKind, id: str) -> bool:
        """False if there was none."""
        ...


class Embedder(Protocol):
    """Any model of config.MODELS, by name."""

    def available(self) -> bool:
        """Whether torch and transformers are installed (the `embed` extra), without loading any model."""
        ...

    def embed(self, model: str, texts: list[str], max_tokens: int) -> list[list[float]]:
        """What is longer than `max_tokens` is cut: whoever calls checks the lengths first. UpstreamDown if the model
        can't be loaded."""
        ...

    def tokens(self, model: str, text: str) -> int:
        """With the model's special tokens, as it reads the text."""
        ...

    def prefix_tokens(self, model: str) -> int | None:
        """The tokens of the model's passage prefix, without special tokens (feature 062), loading only its
        tokenizer; 0 without a prefix; None if it can't be counted (no `embed` extra, or the tokenizer can't load)."""
        ...
