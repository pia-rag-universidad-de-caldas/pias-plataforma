"""The vectors as batches of data. Every node goes in `merge`: the text and everything else chunking wrote stays (and,
on a FRAGMENTOS, the vectors of the other models). Saving vectors deletes nothing; only deleting an embeddings
experiment has a replace_from, its own EXP_EMBEDDINGS (feature 055)."""

from collections.abc import Sequence

from common.clock import now
from embeddings.config import MODEL_VERSION
from embeddings.models import (
    DocumentVectors,
    EmbeddableChunk,
    EmbeddingConfig,
    EmbedProperties,
    GraphBatch,
    GraphLabel,
    GraphLink,
    GraphNode,
    GraphRelation,
    NodeKey,
)

from .identity import Identity
from .indexes import embedded_over_key, fingerprint_key, limit_key, vector_property

ACTIVITY = "actividad"  # on the official JSON (feature 057): the course's name, read from its header
ACTIVITY_CODE = "codigo_actividad"  # and its code; data's full-text index of the documents reads both


def document_batch(
    sha256: str,
    chunks: Sequence[EmbeddableChunk],
    vectors: Sequence[list[float]],
    config: EmbeddingConfig,
    fingerprint: str,
    identity: Identity | None = None,
    chunking: str | None = None,
) -> GraphBatch:
    """The official chunks (FRAGMENTOS) of a document with their vectors in the model's property, and on its JSON the
    model's fingerprint and limit, the chunks it was calculated over (`chunking`, the JSON's huella_chunking) and the
    course (`identity`): one batch, so that a document is embedded whole or not at all."""
    property = vector_property(config.model)
    nodes = [
        GraphNode(NodeKey(GraphLabel.FRAGMENTOS, c.id), {property: v}) for c, v in zip(chunks, vectors, strict=True)
    ]
    document: dict[str, object] = {
        **DocumentVectors(embebido_en=now()),
        fingerprint_key(config.model): fingerprint,
        limit_key(config.model): config.max_tokens,
        **marked(config.model, identity, chunking),
    }
    nodes.append(GraphNode(NodeKey(GraphLabel.JSON, sha256), document))
    return GraphBatch(nodes)


def marked(model: str, identity: Identity | None, chunking: str | None) -> dict[str, object]:
    """What the JSON says of what was embedded: over which chunks (none: nothing) and which course (None removes it
    in merge: a course that can't be read any more isn't kept)."""
    found: dict[str, object] = {embedded_over_key(model): chunking} if chunking else {}
    if identity is not None:
        found |= {ACTIVITY: identity.name, ACTIVITY_CODE: identity.code}
    return found


def marked_batch(sha256: str, model: str, identity: Identity, chunking: str | None) -> GraphBatch:
    """Only the JSON's marks, for a document whose vectors didn't change (embedded before feature 057)."""
    return GraphBatch([GraphNode(NodeKey(GraphLabel.JSON, sha256), marked(model, identity, chunking))])


def embed_id(experiment: str, chunk: str) -> str:
    """<embeddings experiment>:<chunk id>: one EXP_EMBED per chunk and experiment."""
    return f"{experiment}:{chunk}"


def experiment_batch(
    chunks: Sequence[EmbeddableChunk], vectors: Sequence[list[float]], config: EmbeddingConfig
) -> GraphBatch:
    """One EXP_EMBED per EXP_CHUNK of one document of a chunking experiment, with its vector, hanging from the chunk
    (EXP_TIENE_VECTOR) and from the embeddings experiment that calculated it (config.experiment, EXP_GENERA_VECTOR):
    two experiments over the same chunks never step on each other. The chunks and the official JSON aren't touched."""
    experiment = config.experiment or ""
    owner = NodeKey(GraphLabel.EXP_EMBEDDINGS, experiment)
    property = vector_property(config.model)
    nodes: list[GraphNode] = []
    links: list[GraphLink] = []
    for c, v in zip(chunks, vectors, strict=True):
        embed = NodeKey(GraphLabel.EXP_EMBED, embed_id(experiment, c.id))
        nodes.append(
            GraphNode(embed, {**EmbedProperties(modelo=config.model, version_embedding=MODEL_VERSION), property: v})
        )
        links.append(GraphLink(GraphRelation.EXP_TIENE_VECTOR, NodeKey(GraphLabel.EXP_CHUNK, c.id), embed))
        links.append(GraphLink(GraphRelation.EXP_GENERA_VECTOR, owner, embed))
    return GraphBatch(nodes, links)


def cleared_batch(experiment: str) -> GraphBatch:
    """Removes every EXP_EMBED the embeddings experiment calculated (replace_from its EXP_EMBEDDINGS: the chunks and
    the other experiments' vectors stay)."""
    return GraphBatch([], replace_from=NodeKey(GraphLabel.EXP_EMBEDDINGS, experiment))


def unfingerprinted_batch(sha256s: Sequence[str], model: str) -> GraphBatch:
    """Removes that model's fingerprint and limit from these official JSON (a null removes a property in merge)."""
    cleared: dict[str, object] = {fingerprint_key(model): None, limit_key(model): None}
    return GraphBatch([GraphNode(NodeKey(GraphLabel.JSON, sha256), cleared) for sha256 in sha256s])
