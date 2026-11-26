"""ProgressRepository: how far parsing and chunking went over the current files, read from what they left in the graph
(features 042 and 043). It never writes.

- parsing: over the current RAW nodes (vigente), done = estado_parseo `parseado` (and, if a fingerprint is given, with
  that fingerprint: another one counts as missing).
- chunking: over the parsed JSON nodes (estado `parseado` or `parcial`), done = estado_chunking `fragmentado` (and, if
  a fingerprint of a chunking configuration is given, chunked with it over the parse the JSON has now: config_chunking
  is that fingerprint and parseo_chunkeado its fingerprint_parseo; feature 045).
- embeddings: over the chunked JSON nodes (estado_chunking `fragmentado`), done = embedded with a model over the
  chunks the JSON has now: the model's fingerprint huella_<property> is there and huella_chunking_<property> (the
  huella_chunking it was embedded over) is the JSON's huella_chunking. The property (`embedding_<model>_<dim>`) comes
  from whoever asks (embeddings knows the models) and goes as a parameter: the keys are read with j[$key].

The ids are listed by `done` (True: done, False: missing, None: all of them, feature 059), ordered by sha256.

The property names are those parsing and chunking store; they are the graph's contract (models/stored.py of each)."""

from typing import LiteralString

from data.models import GraphAdapter, GraphRow, Parameters

from .cypher import integer

_RAW: LiteralString = """
MATCH (r:RAW) WHERE coalesce(r.vigente, true) = true
WITH r, coalesce(r.estado_parseo = 'parseado' AND ($fingerprint IS NULL OR r.fingerprint_parseo = $fingerprint), false)
     AS done
"""
_JSON: LiteralString = """
MATCH (j:JSON) WHERE j.estado IN ['parseado', 'parcial']
WITH j AS r, coalesce(j.estado_chunking = 'fragmentado' AND ($fingerprint IS NULL OR
     (j.config_chunking = $fingerprint AND j.parseo_chunkeado = j.fingerprint_parseo)), false) AS done
"""
_EMBEDDED: LiteralString = """
MATCH (j:JSON) WHERE j.estado_chunking = 'fragmentado'
WITH j AS r, coalesce(j[$fingerprint_key] IS NOT NULL AND j[$chunking_key] = j.huella_chunking, false) AS done
"""
_PARSING_COUNTS: LiteralString = """
RETURN count(r) AS total,
       sum(CASE WHEN done THEN 1 ELSE 0 END) AS done,
       sum(CASE WHEN r.estado_parseo = 'parcial' THEN 1 ELSE 0 END) AS partial,
       sum(CASE WHEN r.estado_parseo = 'error' THEN 1 ELSE 0 END) AS errors,
       sum(CASE WHEN r.estado_parseo IS NULL THEN 1 ELSE 0 END) AS never
"""
_CHUNKING_COUNTS: LiteralString = """
RETURN count(r) AS total,
       sum(CASE WHEN done THEN 1 ELSE 0 END) AS done,
       sum(0) AS partial,  // a constant would be a grouping key: no row without documents
       sum(CASE WHEN r.estado_chunking = 'error' THEN 1 ELSE 0 END) AS errors,
       sum(CASE WHEN r.estado_chunking IS NULL THEN 1 ELSE 0 END) AS never
"""
_EMBEDDING_COUNTS: LiteralString = """
RETURN count(r) AS total,
       sum(CASE WHEN done THEN 1 ELSE 0 END) AS done,
       sum(CASE WHEN NOT done AND r[$fingerprint_key] IS NOT NULL THEN 1 ELSE 0 END) AS partial,
       sum(0) AS errors,
       sum(CASE WHEN r[$fingerprint_key] IS NULL THEN 1 ELSE 0 END) AS never
"""
# Feature 062: over the chunked documents (EXP_DOCUMENTO fragmentado) of the chunking experiment an embeddings
# experiment embeds (EXP_USA), done = every chunk of it has a vector of that embeddings experiment (a document is
# embedded in one batch, and chunking it again removes its chunks and their vectors: then it is missing again).
_EXPERIMENT_EMBEDDED: LiteralString = """
MATCH (x:EXP_EMBEDDINGS {id: $experiment})-[:EXP_USA]->(:EXPERIMENTO)-[:EXP_TIENE_DOCUMENTO]->(d:EXP_DOCUMENTO)
WHERE d.estado = 'fragmentado'
WITH d, NOT EXISTS {
       MATCH (d)-[:EXP_TIENE_SECCION]->(:EXP_SECCION)-[:EXP_TIENE_CHUNK]->(c:EXP_CHUNK)
       WHERE NOT EXISTS { MATCH (c)-[:EXP_TIENE_VECTOR]->(:EXP_EMBED)<-[:EXP_GENERA_VECTOR]-(x) } } AS done
WITH d AS r, done
"""
_EXPERIMENT_COUNTS: LiteralString = """
RETURN count(r) AS total,
       sum(CASE WHEN done THEN 1 ELSE 0 END) AS done,
       sum(0) AS partial,
       sum(0) AS errors,
       sum(CASE WHEN done THEN 0 ELSE 1 END) AS never
"""
_EXPERIMENT_IDS: LiteralString = """
WITH r, done WHERE $done IS NULL OR done = $done
RETURN coalesce(r.sha256, last(split(r.id, ':'))) AS id ORDER BY id SKIP $skip LIMIT $limit
"""
_EMBEDDINGS_EXPERIMENT: LiteralString = "MATCH (x:EXP_EMBEDDINGS {id: $experiment}) RETURN x.id AS id"
_IDS: LiteralString = """
WITH r, done WHERE $done IS NULL OR done = $done
RETURN r.id AS id ORDER BY id SKIP $skip LIMIT $limit
"""


def embedding_keys(property: str) -> dict[str, str]:
    """The JSON keys of a model's vectors (embeddings writes them; feature 055 and 057)."""
    return {"fingerprint_key": "huella_" + property, "chunking_key": "huella_chunking_" + property}


def _counts(row: GraphRow) -> dict[str, int]:
    return {key: integer(row[key]) for key in ("total", "done", "partial", "errors", "never")}


class ProgressRepository:
    def __init__(self, graph: GraphAdapter) -> None:
        self._graph = graph

    def parsing_counts(self, fingerprint: str | None) -> dict[str, int]:
        return _counts(self._graph.read(_RAW + _PARSING_COUNTS, {"fingerprint": fingerprint})[0])

    def parsing_ids(self, done: bool | None, fingerprint: str | None, skip: int, limit: int) -> list[str]:
        rows = self._graph.read(_RAW + _IDS, {"fingerprint": fingerprint, "done": done, "skip": skip, "limit": limit})
        return [str(row["id"]) for row in rows]

    def chunking_counts(self, fingerprint: str | None = None) -> dict[str, int]:
        return _counts(self._graph.read(_JSON + _CHUNKING_COUNTS, {"fingerprint": fingerprint})[0])

    def chunking_ids(self, done: bool | None, fingerprint: str | None, skip: int, limit: int) -> list[str]:
        rows = self._graph.read(_JSON + _IDS, {"fingerprint": fingerprint, "done": done, "skip": skip, "limit": limit})
        return [str(row["id"]) for row in rows]

    def embedding_counts(self, property: str) -> dict[str, int]:
        """`partial`: embedded with that model, but over chunks the JSON no longer has (or before feature 057)."""
        return _counts(self._graph.read(_EMBEDDED + _EMBEDDING_COUNTS, embedding_keys(property))[0])

    def embeddings_experiment_exists(self, experiment: str) -> bool:
        return bool(self._graph.read(_EMBEDDINGS_EXPERIMENT, {"experiment": experiment}))

    def experiment_embedding_counts(self, experiment: str) -> dict[str, int]:
        """Feature 062: `never` = the chunked documents of its chunking experiment without its vectors."""
        rows = self._graph.read(_EXPERIMENT_EMBEDDED + _EXPERIMENT_COUNTS, {"experiment": experiment})
        return _counts(rows[0]) if rows else dict.fromkeys(("total", "done", "partial", "errors", "never"), 0)

    def experiment_embedding_ids(self, done: bool | None, experiment: str, skip: int, limit: int) -> list[str]:
        parameters: Parameters = {"experiment": experiment, "done": done, "skip": skip, "limit": limit}
        rows = self._graph.read(_EXPERIMENT_EMBEDDED + _EXPERIMENT_IDS, parameters)
        return [str(row["id"]) for row in rows]

    def embedding_ids(self, done: bool | None, property: str, skip: int, limit: int) -> list[str]:
        parameters: Parameters = {**embedding_keys(property), "done": done, "skip": skip, "limit": limit}
        rows = self._graph.read(_EMBEDDED + _IDS, parameters)
        return [str(row["id"]) for row in rows]
