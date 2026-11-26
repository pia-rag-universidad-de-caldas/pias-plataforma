"""VectorRepository (features 046 and 055): vector indexes and the search over them. The index name and the vector
always go as parameters; the label (a value of the Label enum) and the vector property (validated by cypher.py) are
concatenated.

Neo4j admits ONE vector index per label and property. Since feature 055 the property carries the model and its
dimensions (`embedding_<model>_<dim>`): each model has its own property and its own index, side by side.

The search uses db.index.vector.queryNodes, which Neo4j 2026 marks as deprecated in favour of the SEARCH clause; SEARCH
doesn't accept the index as a parameter (it would have to be concatenated), so the procedure stays until it goes.
"""

from typing import LiteralString

from data.models import GraphAdapter, GraphRow, Label, Parameters

from .cypher import integer, name, vector_property

_FIND: LiteralString = """
SHOW VECTOR INDEXES YIELD name, labelsOrTypes, properties, options
WHERE name = $name
RETURN name, labelsOrTypes[0] AS label, properties[0] AS property,
       options.indexConfig['vector.dimensions'] AS dimensions
"""

_ON: LiteralString = """
SHOW VECTOR INDEXES YIELD name, labelsOrTypes, properties, options
WHERE labelsOrTypes[0] = $label AND properties[0] = $property
RETURN name, labelsOrTypes[0] AS label, properties[0] AS property,
       options.indexConfig['vector.dimensions'] AS dimensions
"""

# Only the official chunks of a chunked document; the file's origin and code come from its RAW (feature 042).
_SEARCH: LiteralString = """
CALL db.index.vector.queryNodes($index, $candidates, $vector) YIELD node AS f, score
MATCH (j:JSON)-[:TIENE_SECCION]->(:SECCION)-[:TIENE_FRAGMENTO]->(f)
WHERE j.estado_chunking = 'fragmentado'
OPTIONAL MATCH (j)-[:VIENE_DE]->(r:RAW)
RETURN f.id AS id, score, f.texto AS text, f.encabezados AS headings, f.paginas AS pages,
       j.id AS sha256, r.origen AS origin, r.codigo AS code, j.actividad AS activity
ORDER BY score DESC
LIMIT $k
"""
# Only the chunks of some documents (feature 057: the course a question names): an exact search over their vectors,
# with the same score the index gives (vector.similarity.cosine, 0 to 1). A few documents have tens of chunks.
_DOCUMENTS_SEARCH: LiteralString = """
MATCH (j:JSON)-[:TIENE_SECCION]->(:SECCION)-[:TIENE_FRAGMENTO]->(f:FRAGMENTOS)
WHERE j.id IN $sha256s AND j.estado_chunking = 'fragmentado' AND f[$property] IS NOT NULL
WITH j, f, vector.similarity.cosine(f[$property], $vector) AS score
OPTIONAL MATCH (j)-[:VIENE_DE]->(r:RAW)
RETURN f.id AS id, score, f.texto AS text, f.encabezados AS headings, f.paginas AS pages,
       j.id AS sha256, r.origen AS origin, r.codigo AS code, j.actividad AS activity
ORDER BY score DESC
LIMIT $k
"""
CANDIDATES = 10  # the filter runs after the index: k * CANDIDATES are asked for (as piaa-rag does)

# The chunks of one embeddings experiment (features 048 and 055): the EXP_EMBED index of a model holds the vectors of
# every experiment that used it; only those its EXP_EMBEDDINGS generated count, and each one goes up to its EXP_CHUNK,
# its EXP_SECCION (the sha256) and the RAW of that sha256 (the origin and the code).
_EXPERIMENT_SEARCH: LiteralString = """
CALL db.index.vector.queryNodes($index, $candidates, $vector) YIELD node AS v, score
MATCH (:EXP_EMBEDDINGS {id: $experiment})-[:EXP_GENERA_VECTOR]->(v)
MATCH (c:EXP_CHUNK)-[:EXP_TIENE_VECTOR]->(v)
MATCH (s:EXP_SECCION)-[:EXP_TIENE_CHUNK]->(c)
OPTIONAL MATCH (r:RAW {id: s.sha256})
OPTIONAL MATCH (j:JSON {id: s.sha256})
RETURN c.id AS id, score, c.texto AS text, c.encabezados AS headings, c.paginas AS pages,
       s.sha256 AS sha256, r.origen AS origin, r.codigo AS code, j.actividad AS activity
ORDER BY score DESC
LIMIT $k
"""
# One index holds the vectors of every experiment of a model: the filter leaves out more than for the official ones.
EXPERIMENT_CANDIDATES = 50
MAX_CANDIDATES = 10_000  # the most queryNodes is asked for
REMOVE_BATCH = 1000  # nodes per transaction when a vector property is removed (feature 055)


class VectorIndexConflict(Exception):
    """An index with that name exists with another definition: 409."""


class VectorRepository:
    def __init__(self, graph: GraphAdapter) -> None:
        self._graph = graph

    def find(self, index: str) -> GraphRow | None:
        """{name, label, property, dimensions}, or None if there is no vector index with that name."""
        rows = self._graph.read(_FIND, {"name": index})
        return rows[0] if rows else None

    def on(self, label: Label, property: str) -> GraphRow | None:
        """The vector index on that label and property, if there is one (Neo4j admits one)."""
        rows = self._graph.read(_ON, {"label": label.value, "property": property})
        return rows[0] if rows else None

    def ensure(self, index: str, label: Label, property: str, dimensions: int) -> GraphRow:
        """Creates it if missing; an existing one must be the same (IF NOT EXISTS alone would hide the difference), and
        no other index may hold the property's vectors. GraphError if the property isn't a vector property."""
        found = self.find(index)
        if found is None:
            other = self.on(label, property)
            if other is not None:
                raise VectorIndexConflict(
                    f"{other['name']} already indexes {label.value}.{property} ({other['dimensions']} dimensions):"
                    " Neo4j admits one per label and property"
                )
            self._graph.write(
                "CREATE VECTOR INDEX $name IF NOT EXISTS FOR (n:"
                + name(label)
                + ") ON n."
                + vector_property(property)
                + " OPTIONS { indexConfig: { `vector.dimensions`: $dimensions,"
                " `vector.similarity_function`: 'cosine' } }",
                {"name": index, "dimensions": dimensions},
            )
            found = self.find(index)
            if found is None:
                raise VectorIndexConflict(f"{index} was created but can't be read back")
        if (found["label"], found["property"], integer(found["dimensions"])) != (label.value, property, dimensions):
            where = f"{found['label']}.{found['property']}, {found['dimensions']} dimensions"
            raise VectorIndexConflict(f"{index} already exists on {where}")
        return found

    def drop(self, index: str, drop_property: bool = False) -> int | None:
        """None if there was no such index. Without `drop_property` the vectors stay on their nodes and 0 is answered;
        with it, the index's property is removed from every node of its label too (feature 055: a model's vectors
        go), and how many nodes lost it is answered. The index goes first: nothing searches a half-removed property."""
        found = self.find(index)
        if found is None:
            return None
        self._graph.write("DROP INDEX $name IF EXISTS", {"name": index})
        if not drop_property:
            return 0
        return self.remove_property(Label(str(found["label"])), str(found["property"]))

    def remove_property(self, label: Label, property: str) -> int:
        """Removes a vector property from every node of `label` that has it, REMOVE_BATCH nodes per transaction."""
        removed = 0
        while True:
            rows = self._graph.write(
                "MATCH (n:"
                + name(label)
                + ") WHERE n."
                + vector_property(property)
                + " IS NOT NULL WITH n LIMIT $batch REMOVE n."
                + vector_property(property)
                + " RETURN count(*) AS removed",
                {"batch": REMOVE_BATCH},
            )
            done = integer(rows[0]["removed"]) if rows else 0
            removed += done
            if done < REMOVE_BATCH:
                return removed

    def search(self, index: str, vector: list[float], k: int) -> list[GraphRow]:
        return self._graph.read(_SEARCH, {"index": index, "vector": vector, "k": k, "candidates": k * CANDIDATES})

    def search_documents(self, property: str, vector: list[float], k: int, sha256s: list[str]) -> list[GraphRow]:
        """Only the official chunks of those documents, by the vectors of `property` (the index's)."""
        parameters: Parameters = {"property": property, "vector": vector, "k": k, "sha256s": list(sha256s)}
        return self._graph.read(_DOCUMENTS_SEARCH, parameters)

    def search_experiment(self, index: str, vector: list[float], k: int, experiment: str) -> list[GraphRow]:
        """Only the EXP_CHUNK whose vector (EXP_EMBED) the embeddings experiment `experiment` calculated; each row is
        the chunk (its id, text...), never the EXP_EMBED."""
        candidates = min(k * EXPERIMENT_CANDIDATES, MAX_CANDIDATES)
        parameters: Parameters = {
            "index": index,
            "vector": vector,
            "k": k,
            "candidates": candidates,
            "experiment": experiment,
        }
        return self._graph.read(_EXPERIMENT_SEARCH, parameters)
