"""VectorMigration (feature 055): the vectors stored before 055, moved to the shape of 055. Run once (the
`prueba-chunking migrate-vectors` command); idempotent: a second run finds nothing to move, and one cut halfway is
finished by the next. With `simulate`, it only counts.

    FRAGMENTOS.embedding            → FRAGMENTOS.embedding_<model>_<dim> (modelo_embedding, version_embedding go)
    JSON.huella_embedding           → JSON.huella_embedding_<model>_<dim> (modelo_embedding goes)
    JSON.limite_tokens_embedding    → JSON.limite_tokens_embedding_<model>_<dim>
    EXP_CHUNK.embedding (experimento_embedding = an EXP_EMBEDDINGS)
                                    → (:EXP_CHUNK)-[:EXP_TIENE_VECTOR]->(:EXP_EMBED {id: <exp>:<chunk>})
                                      <-[:EXP_GENERA_VECTOR]-(:EXP_EMBEDDINGS)
    EXP_CHUNK.embedding of no experiment → removed (nobody can search it: its experiment was deleted)
    vector indexes on `embedding`   → dropped; one per vector property present, on FRAGMENTOS and EXP_EMBED

data knows no model: the names (`embedding_<model>_<dim>` and the index of a property) are embeddings' and come in a
VectorNaming that server builds. The model of a vector is its `modelo_embedding`, or `fallback_model` (the active one)
if it has none; its dimensions, the length of the vector. Everything goes in transactions of BATCH nodes.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import LiteralString

from data.models import GraphAdapter, GraphValue, Label, Parameters
from data.schema.vector_rules import VECTOR_LABELS, valid_vector_property

from .cypher import integer, name, vector_property
from .vector_repository import VectorRepository

BATCH = 1000

_LEGACY_INDEXES: LiteralString = """
SHOW VECTOR INDEXES YIELD name, properties WHERE properties[0] = 'embedding' RETURN name
"""
_FRAGMENT_GROUPS: LiteralString = """
MATCH (f:FRAGMENTOS) WHERE f.embedding IS NOT NULL
RETURN coalesce(f.modelo_embedding, $fallback) AS model, size(f.embedding) AS dimensions, count(*) AS nodes
ORDER BY model, dimensions
"""
_DOCUMENT_GROUPS: LiteralString = """
MATCH (j:JSON) WHERE j.huella_embedding IS NOT NULL
RETURN coalesce(j.modelo_embedding, $fallback) AS model, count(*) AS nodes ORDER BY model
"""
_EXPERIMENT_GROUPS: LiteralString = """
MATCH (c:EXP_CHUNK) WHERE c.embedding IS NOT NULL
  AND EXISTS { MATCH (e:EXP_EMBEDDINGS) WHERE e.id = c.experimento_embedding }
RETURN coalesce(c.modelo_embedding, $fallback) AS model, size(c.embedding) AS dimensions, count(*) AS nodes
ORDER BY model, dimensions
"""
_ORPHANS: LiteralString = """
MATCH (c:EXP_CHUNK) WHERE c.embedding IS NOT NULL
  AND NOT EXISTS { MATCH (e:EXP_EMBEDDINGS) WHERE e.id = c.experimento_embedding }
RETURN count(*) AS nodes
"""
_MOVE_DOCUMENTS: LiteralString = """
MATCH (j:JSON) WHERE j.huella_embedding IS NOT NULL AND coalesce(j.modelo_embedding, $fallback) = $model
WITH j LIMIT $batch
SET j[$fingerprint] = j.huella_embedding, j[$limit] = j.limite_tokens_embedding
REMOVE j.huella_embedding, j.limite_tokens_embedding, j.modelo_embedding
RETURN count(*) AS moved
"""
_DROP_ORPHANS: LiteralString = """
MATCH (c:EXP_CHUNK) WHERE c.embedding IS NOT NULL
  AND NOT EXISTS { MATCH (e:EXP_EMBEDDINGS) WHERE e.id = c.experimento_embedding }
WITH c LIMIT $batch
REMOVE c.embedding, c.modelo_embedding, c.version_embedding, c.experimento_embedding
RETURN count(*) AS moved
"""


@dataclass(frozen=True)
class VectorNaming:
    """What embeddings names (server builds it from embeddings.domain): data knows no model."""

    property: Callable[[str, int], str]  # (model, dimensions) → embedding_<model>_<dim>
    index: Callable[[Label, str], str]  # (label, vector property) → the name of its index
    fallback_model: str  # the model of a vector stored without modelo_embedding: the active one
    dimensions: Mapping[str, int] = field(default_factory=dict)  # of each served model (a JSON holds no vector)


@dataclass(frozen=True)
class VectorGroup:
    model: str
    dimensions: int
    property: str  # where they go
    nodes: int


@dataclass(frozen=True)
class MigrationReport:
    """What a migration moved (or, with simulate, would move)."""

    simulate: bool
    fragments: list[VectorGroup]  # FRAGMENTOS.embedding → their property
    documents: list[VectorGroup]  # JSON fingerprints → per model
    unknown_documents: int  # JSON fingerprints of a model whose dimensions aren't known: left as they are
    experiment_vectors: list[VectorGroup]  # EXP_CHUNK.embedding → EXP_EMBED
    orphan_vectors: int  # EXP_CHUNK.embedding of no existing embeddings experiment: removed
    dropped_indexes: list[str]  # the indexes on `embedding`
    created_indexes: list[str]  # one per vector property present that had none

    @property
    def pending(self) -> bool:
        """Whether there was anything to do (a second run answers False)."""
        moved = self.fragments or self.documents or self.experiment_vectors or self.orphan_vectors
        return bool(moved or self.dropped_indexes or self.created_indexes)


def _text(value: GraphValue) -> str:
    return str(value)


class VectorMigration:
    def __init__(self, graph: GraphAdapter, naming: VectorNaming) -> None:
        self._graph = graph
        self._naming = naming
        self._vectors = VectorRepository(graph)

    def _groups(self, cypher: LiteralString) -> list[VectorGroup]:
        rows = self._graph.read(cypher, {"fallback": self._naming.fallback_model})
        groups: list[VectorGroup] = []
        for row in rows:
            model, dimensions = _text(row["model"]), integer(row["dimensions"])
            groups.append(
                VectorGroup(model, dimensions, self._naming.property(model, dimensions), integer(row["nodes"]))
            )
        return groups

    def _documents(self, fragments: list[VectorGroup]) -> tuple[list[VectorGroup], int]:
        """The JSON fingerprints by model; the dimensions are those of the served model, or of its vectors."""
        seen = {g.model: g.dimensions for g in fragments}
        known: list[VectorGroup] = []
        unknown = 0
        for row in self._graph.read(_DOCUMENT_GROUPS, {"fallback": self._naming.fallback_model}):
            model, nodes = _text(row["model"]), integer(row["nodes"])
            dimensions = self._naming.dimensions.get(model) or seen.get(model)
            if dimensions is None:
                unknown += nodes
            else:
                known.append(VectorGroup(model, dimensions, self._naming.property(model, dimensions), nodes))
        return known, unknown

    def _loop(self, cypher: LiteralString, parameters: Parameters) -> int:
        """Runs `cypher` (which moves at most $batch nodes and answers `moved`) until nothing is left."""
        total = 0
        while True:
            rows = self._graph.write(cypher, {**parameters, "batch": BATCH})
            moved = integer(rows[0]["moved"]) if rows else 0
            total += moved
            if moved < BATCH:
                return total

    def _present(self, label: Label) -> dict[str, int]:
        """The vector properties of 055 on the nodes of `label`, with their dimensions."""
        rows = self._graph.read(
            "MATCH (n:" + name(label) + ") UNWIND [k IN keys(n) WHERE k =~ 'embedding_[a-z0-9_]+'] AS property "
            "RETURN property, max(size(n[property])) AS dimensions"
        )
        return {
            _text(r["property"]): integer(r["dimensions"]) for r in rows if valid_vector_property(_text(r["property"]))
        }

    def _indexes(self, wanted: dict[Label, dict[str, int]], simulate: bool) -> list[str]:
        created: list[str] = []
        for label, properties in wanted.items():
            for property, dimensions in sorted(properties.items()):
                if self._vectors.on(label, property) is not None:
                    continue
                index = self._naming.index(label, property)
                if not simulate:
                    self._vectors.ensure(index, label, property, dimensions)
                created.append(index)
        return created

    def run(self, simulate: bool = False) -> MigrationReport:
        legacy = [_text(row["name"]) for row in self._graph.read(_LEGACY_INDEXES)]
        fragments = self._groups(_FRAGMENT_GROUPS)
        documents, unknown = self._documents(fragments)
        experiments = self._groups(_EXPERIMENT_GROUPS)
        orphans = integer(self._graph.read(_ORPHANS)[0]["nodes"])
        if not simulate:
            for index in legacy:  # before anything: the new indexes may have the same names
                self._graph.write("DROP INDEX $name IF EXISTS", {"name": index})
            for group in fragments:
                self._move_fragments(group)
            for group in documents:
                self._loop(
                    _MOVE_DOCUMENTS,
                    {
                        "fallback": self._naming.fallback_model,
                        "model": group.model,
                        "fingerprint": "huella_" + group.property,
                        "limit": "limite_tokens_" + group.property,
                    },
                )
            for group in experiments:
                self._move_experiment_vectors(group)
            self._loop(_DROP_ORPHANS, {})
        wanted: dict[Label, dict[str, int]] = {label: self._present(label) for label in VECTOR_LABELS}
        if simulate:  # what isn't moved yet
            wanted[Label.FRAGMENTOS] |= {g.property: g.dimensions for g in fragments}
            wanted[Label.EXP_EMBED] |= {g.property: g.dimensions for g in experiments}
        created = self._indexes(wanted, simulate)
        return MigrationReport(simulate, fragments, documents, unknown, experiments, orphans, legacy, created)

    def _move_fragments(self, group: VectorGroup) -> None:
        target = vector_property(group.property)
        self._loop(
            "MATCH (f:FRAGMENTOS) WHERE f.embedding IS NOT NULL AND coalesce(f.modelo_embedding, $fallback) = $model"
            " AND size(f.embedding) = $dimensions WITH f LIMIT $batch SET f."
            + target
            + " = f.embedding REMOVE f.embedding, f.modelo_embedding, f.version_embedding RETURN count(*) AS moved",
            {"fallback": self._naming.fallback_model, "model": group.model, "dimensions": group.dimensions},
        )

    def _move_experiment_vectors(self, group: VectorGroup) -> None:
        target = vector_property(group.property)
        self._loop(
            "MATCH (c:EXP_CHUNK) WHERE c.embedding IS NOT NULL AND coalesce(c.modelo_embedding, $fallback) = $model"
            " AND size(c.embedding) = $dimensions"
            " MATCH (e:EXP_EMBEDDINGS) WHERE e.id = c.experimento_embedding"
            " WITH c, e LIMIT $batch"
            " MERGE (v:EXP_EMBED {id: e.id + ':' + c.id})"
            " SET v.modelo = $model, v.version_embedding = c.version_embedding, v." + target + " = c.embedding"
            " MERGE (c)-[:EXP_TIENE_VECTOR]->(v) MERGE (e)-[:EXP_GENERA_VECTOR]->(v)"
            " REMOVE c.embedding, c.modelo_embedding, c.version_embedding, c.experimento_embedding"
            " RETURN count(*) AS moved",
            {"fallback": self._naming.fallback_model, "model": group.model, "dimensions": group.dimensions},
        )
