"""ProgressRepository: how far parsing and chunking went over the current files, read from what they left in the graph
(features 042 and 043). It never writes.

- parsing: over the current RAW nodes (vigente), done = estado_parseo `parseado` (and, if a fingerprint is given, with
  that fingerprint: another one counts as missing).
- chunking: over the parsed JSON nodes (estado `parseado` or `parcial`), done = estado_chunking `fragmentado` (and, if
  a fingerprint of a chunking configuration is given, chunked with it over the parse the JSON has now: config_chunking
  is that fingerprint and parseo_chunkeado its fingerprint_parseo; feature 045).

The property names are those parsing and chunking store; they are the graph's contract (models/stored.py of each)."""

from typing import LiteralString

from data.models import GraphAdapter, GraphRow

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
_IDS: LiteralString = """
WITH r, done WHERE done = $done
RETURN r.id AS id ORDER BY id SKIP $skip LIMIT $limit
"""


def _counts(row: GraphRow) -> dict[str, int]:
    return {key: integer(row[key]) for key in ("total", "done", "partial", "errors", "never")}


class ProgressRepository:
    def __init__(self, graph: GraphAdapter) -> None:
        self._graph = graph

    def parsing_counts(self, fingerprint: str | None) -> dict[str, int]:
        return _counts(self._graph.read(_RAW + _PARSING_COUNTS, {"fingerprint": fingerprint})[0])

    def parsing_ids(self, done: bool, fingerprint: str | None, skip: int, limit: int) -> list[str]:
        rows = self._graph.read(_RAW + _IDS, {"fingerprint": fingerprint, "done": done, "skip": skip, "limit": limit})
        return [str(row["id"]) for row in rows]

    def chunking_counts(self, fingerprint: str | None = None) -> dict[str, int]:
        return _counts(self._graph.read(_JSON + _CHUNKING_COUNTS, {"fingerprint": fingerprint})[0])

    def chunking_ids(self, done: bool, fingerprint: str | None, skip: int, limit: int) -> list[str]:
        rows = self._graph.read(_JSON + _IDS, {"fingerprint": fingerprint, "done": done, "skip": skip, "limit": limit})
        return [str(row["id"]) for row in rows]
