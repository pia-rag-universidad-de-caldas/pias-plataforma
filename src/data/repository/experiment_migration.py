"""ExperimentMigration (feature 055 part b): the chunking experiments stored before 055b, moved to its shape, and what
was left from before feature 043 removed. Run once (the `prueba-chunking migrate-experiments` command); idempotent: a
second run finds nothing to do, and one cut halfway is finished by the next (each step goes in statements of at most
BATCH rows, each one its own transaction, and creates the new shape before deleting the old one). With `simulate`, it
only counts.

    (:EXPERIMENTO)-[:EXP_USA {summary}]->(:JSON)
        → (:EXPERIMENTO)-[:EXP_TIENE_DOCUMENTO]->(:EXP_DOCUMENTO {id: <exp>:<sha256>, summary})-[:EXP_DE]->(:JSON)
    (:EXPERIMENTO)-[:EXP_GENERA]->(:EXP_SECCION {sha256})
        → (:EXP_DOCUMENTO {id: <exp>:<sha256>})-[:EXP_TIENE_SECCION]->(:EXP_SECCION)
    EXP_DOCUMENTO of before 043 that no EXPERIMENTO uses → removed, with its sections, chunks and their vectors
    EXP_SECCION that hangs from nothing                  → removed, with its chunks and their vectors
    EXP_PUNTUACION (scores of before 043)                → removed

An EXPERIMENTO of before 043 that still uses its (shared) EXP_DOCUMENTO through EXP_USA is not touched: it is only
listed (`legacy_experiments`); `DELETE /chunking/experiments/{id}` removes it, and the next run, its documents.

The old relationship and label names are not in data.models any more (they left the schema): they are written here, as
constants. Nothing goes through the schema: this is Cypher straight on Neo4j, like VectorMigration.
"""

from dataclasses import dataclass
from typing import LiteralString

from data.models import GraphAdapter, GraphValue, Parameters

from .cypher import integer

BATCH = 1000

_USES: LiteralString = "MATCH (:EXPERIMENTO)-[u:EXP_USA]->(:JSON) RETURN count(u) AS nodes"
_GENERATED: LiteralString = (
    "MATCH (:EXPERIMENTO)-[g:EXP_GENERA]->(s:EXP_SECCION) WHERE s.sha256 IS NOT NULL RETURN count(g) AS nodes"
)
_OLD_DOCUMENTS: LiteralString = """
MATCH (d:EXP_DOCUMENTO) WHERE NOT EXISTS { MATCH (:EXPERIMENTO)-[:EXP_TIENE_DOCUMENTO|EXP_USA]->(d) }
RETURN count(d) AS nodes
"""
_ORPHAN_SECTIONS: LiteralString = """
MATCH (s:EXP_SECCION) WHERE NOT EXISTS { MATCH ()-[:EXP_TIENE_SECCION|EXP_GENERA]->(s) }
RETURN count(s) AS nodes
"""
_SCORES: LiteralString = "MATCH (p:EXP_PUNTUACION) RETURN count(p) AS nodes"
_LEGACY: LiteralString = """
MATCH (e:EXPERIMENTO)-[:EXP_USA]->(:EXP_DOCUMENTO) RETURN DISTINCT e.id AS id ORDER BY id
"""

# Each one changes at most $batch rows and answers how many (`moved`); _loop repeats it until fewer come back.
_MOVE_USES: LiteralString = """
MATCH (e:EXPERIMENTO)-[u:EXP_USA]->(j:JSON)
WITH e, u, j LIMIT $batch
MERGE (d:EXP_DOCUMENTO {id: e.id + ':' + j.id})
SET d += properties(u), d.sha256 = j.id
MERGE (e)-[:EXP_TIENE_DOCUMENTO]->(d)
MERGE (d)-[:EXP_DE]->(j)
DELETE u
RETURN count(*) AS moved
"""
# After _MOVE_USES: a section without its EXP_USA (its JSON was deleted) gets a document that says only that it was
# chunked, and an EXP_DE only if the JSON is there.
_MOVE_SECTIONS: LiteralString = """
MATCH (e:EXPERIMENTO)-[g:EXP_GENERA]->(s:EXP_SECCION) WHERE s.sha256 IS NOT NULL
WITH e, g, s LIMIT $batch
MERGE (d:EXP_DOCUMENTO {id: e.id + ':' + s.sha256})
ON CREATE SET d.sha256 = s.sha256, d.estado = 'fragmentado'
MERGE (e)-[:EXP_TIENE_DOCUMENTO]->(d)
MERGE (d)-[:EXP_TIENE_SECCION]->(s)
WITH g, d, s
OPTIONAL MATCH (j:JSON {id: s.sha256})
FOREACH (found IN CASE WHEN j IS NULL THEN [] ELSE [j] END | MERGE (d)-[:EXP_DE]->(found))
DELETE g
RETURN count(*) AS moved
"""
_DROP_OLD_DOCUMENTS: LiteralString = """
MATCH (d:EXP_DOCUMENTO) WHERE NOT EXISTS { MATCH (:EXPERIMENTO)-[:EXP_TIENE_DOCUMENTO|EXP_USA]->(d) }
WITH d LIMIT $batch
OPTIONAL MATCH (d)-[:EXP_TIENE_SECCION]->(s:EXP_SECCION)
OPTIONAL MATCH (s)-[:EXP_TIENE_CHUNK]->(c:EXP_CHUNK)
OPTIONAL MATCH (c)-[:EXP_TIENE_VECTOR]->(v:EXP_EMBED)
WITH d, collect(DISTINCT s) AS sections, collect(DISTINCT c) AS chunks, collect(DISTINCT v) AS vectors
FOREACH (n IN vectors | DETACH DELETE n)
FOREACH (n IN chunks | DETACH DELETE n)
FOREACH (n IN sections | DETACH DELETE n)
DETACH DELETE d
RETURN count(*) AS moved
"""
_DROP_ORPHAN_SECTIONS: LiteralString = """
MATCH (s:EXP_SECCION) WHERE NOT EXISTS { MATCH ()-[:EXP_TIENE_SECCION|EXP_GENERA]->(s) }
WITH s LIMIT $batch
OPTIONAL MATCH (s)-[:EXP_TIENE_CHUNK]->(c:EXP_CHUNK)
OPTIONAL MATCH (c)-[:EXP_TIENE_VECTOR]->(v:EXP_EMBED)
WITH s, collect(DISTINCT c) AS chunks, collect(DISTINCT v) AS vectors
FOREACH (n IN vectors | DETACH DELETE n)
FOREACH (n IN chunks | DETACH DELETE n)
DETACH DELETE s
RETURN count(*) AS moved
"""
_DROP_SCORES: LiteralString = """
MATCH (p:EXP_PUNTUACION) WITH p LIMIT $batch DETACH DELETE p RETURN count(*) AS moved
"""


@dataclass(frozen=True)
class ExperimentMigrationReport:
    """What a migration did (or, with simulate, would do), counted before doing it."""

    simulate: bool
    documents: int  # EXP_USA EXPERIMENTO → JSON that became an EXP_DOCUMENTO
    sections: int  # EXP_GENERA that became an EXP_TIENE_SECCION from its EXP_DOCUMENTO
    old_documents: int  # EXP_DOCUMENTO of before 043 that no experiment uses: removed with what hangs from them
    orphan_sections: int  # EXP_SECCION that hang from nothing: removed with their chunks
    scores: int  # EXP_PUNTUACION: removed
    legacy_experiments: list[str]  # EXPERIMENTO of before 043, left as they are

    @property
    def pending(self) -> bool:
        """Whether there was anything to do (a second run answers False; the legacy experiments don't count)."""
        return bool(self.documents or self.sections or self.old_documents or self.orphan_sections or self.scores)


class ExperimentMigration:
    def __init__(self, graph: GraphAdapter) -> None:
        self._graph = graph

    def _count(self, cypher: LiteralString) -> int:
        rows = self._graph.read(cypher)
        return integer(rows[0]["nodes"]) if rows else 0

    def _loop(self, cypher: LiteralString) -> int:
        """Runs `cypher` until it changes fewer than BATCH rows."""
        total = 0
        parameters: Parameters = {"batch": BATCH}
        while True:
            rows = self._graph.write(cypher, parameters)
            moved = integer(rows[0]["moved"]) if rows else 0
            total += moved
            if moved < BATCH:
                return total

    def run(self, simulate: bool = False) -> ExperimentMigrationReport:
        report = ExperimentMigrationReport(
            simulate=simulate,
            documents=self._count(_USES),
            sections=self._count(_GENERATED),
            old_documents=self._count(_OLD_DOCUMENTS),
            orphan_sections=self._count(_ORPHAN_SECTIONS),
            scores=self._count(_SCORES),
            legacy_experiments=[_text(row["id"]) for row in self._graph.read(_LEGACY)],
        )
        if not simulate:
            # In this order: the new shape first (documents, then the sections under them), and only then what is
            # left over; a section moved under its document is no longer an orphan.
            for cypher in (_MOVE_USES, _MOVE_SECTIONS, _DROP_OLD_DOCUMENTS, _DROP_ORPHAN_SECTIONS, _DROP_SCORES):
                self._loop(cypher)
        return report


def _text(value: GraphValue) -> str:
    return str(value)
