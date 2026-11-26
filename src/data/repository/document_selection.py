"""DocumentSelection (feature 062): which documents a selection takes, for whoever chooses what to process (the
pipeline). data doesn't decide what is processed: it answers which documents of a universe follow the selection.

- universe `parsed`: the JSON nodes parsed (estado `parseado` or `parcial`); `chunked`: those with official chunks
  (estado_chunking `fragmentado`).
- the filters are over the document's RAW (`tipo`, `anio`, `mes`, `semana`): one without a RAW doesn't pass a filter.
- `exclude`: without those a chunking experiment already has (its EXP_DOCUMENTO).

Cypher answers the universe filtered and ordered by sha256 (only the ids); the mode (`all`, `sha256s`, `pages`,
`sample`) is applied here, in pick(). Every value goes as a parameter: nothing of whoever asks is concatenated.
"""

import hashlib
import random
import re
from dataclasses import dataclass
from typing import Literal, LiteralString

from data.models import GraphAdapter, GraphRow, Parameters
from data.schema.selection_rules import Selection

type Universe = Literal["parsed", "chunked"]

_UNIVERSES: dict[str, LiteralString] = {
    "parsed": "MATCH (j:JSON) WHERE j.estado IN ['parseado', 'parcial']",
    "chunked": "MATCH (j:JSON) WHERE j.estado_chunking = 'fragmentado'",
}
_FILTERED: LiteralString = """
OPTIONAL MATCH (j)-[:VIENE_DE]->(r:RAW)
WITH j, r
WHERE (NOT $filtered OR (r IS NOT NULL
       AND (size($types) = 0 OR toLower(r.tipo) IN $types)
       AND ($year IS NULL OR r.anio = $year)
       AND ($month IS NULL OR r.mes =~ $month_pattern)
       AND ($week IS NULL OR r.semana = $week)))
  AND (size($sha256s) = 0 OR j.id IN $sha256s)
  AND ($exclude IS NULL OR NOT EXISTS {
       MATCH (:EXPERIMENTO {id: $exclude})-[:EXP_TIENE_DOCUMENTO]->(:EXP_DOCUMENTO)-[:EXP_DE]->(j) })
RETURN DISTINCT j.id AS id ORDER BY id
"""
_EXPERIMENT: LiteralString = "MATCH (e:EXPERIMENTO {id: $id}) RETURN e.id AS id"
_PERIODS: LiteralString = """
MATCH (j)-[:VIENE_DE]->(r:RAW)
WHERE $exclude IS NULL OR NOT EXISTS {
      MATCH (:EXPERIMENTO {id: $exclude})-[:EXP_TIENE_DOCUMENTO]->(:EXP_DOCUMENTO)-[:EXP_DE]->(j) }
RETURN r.anio AS year, r.mes AS month, r.semana AS week, count(DISTINCT j) AS documents
"""
_LEADING = re.compile(r"0*(\d{1,2})(?:\D.*)?")


@dataclass(frozen=True)
class WeekCount:
    week: str  # as stored: Semana_02
    documents: int


@dataclass(frozen=True)
class MonthCount:
    month: int  # 1-12: what a selection's `month` takes
    name: str  # as stored: 03_Marzo
    documents: int
    weeks: list[WeekCount]


@dataclass(frozen=True)
class YearCount:
    year: int
    documents: int
    months: list[MonthCount]


def month_number(stored: str) -> int | None:
    """03_Marzo → 3; None if `mes` doesn't start with a month."""
    found = _LEADING.fullmatch(stored)
    number = int(found.group(1)) if found else 0
    return number if 1 <= number <= 12 else None


def periods_of(rows: list[GraphRow]) -> list[YearCount]:
    """(year, mes, semana, documents) rows → years, months and weeks with their documents, in order. A RAW without a
    year, or a `mes` that doesn't start with a month, counts only up to where it can."""
    years: dict[int, dict[int, tuple[str, dict[str, int]]]] = {}
    per_year: dict[int, int] = {}
    per_month: dict[tuple[int, int], int] = {}
    for row in rows:
        year, stored, week, count = row.get("year"), row.get("month"), row.get("week"), row.get("documents")
        if not isinstance(year, int) or not isinstance(count, int):
            continue
        per_year[year] = per_year.get(year, 0) + count
        months = years.setdefault(year, {})
        month = month_number(stored) if isinstance(stored, str) else None
        if month is None or not isinstance(stored, str):  # (narrows `stored` for mypy)
            continue
        per_month[(year, month)] = per_month.get((year, month), 0) + count
        weeks = months.setdefault(month, (stored, {}))[1]
        if isinstance(week, str) and week:
            weeks[week] = weeks.get(week, 0) + count
    return [
        YearCount(
            year,
            per_year[year],
            [
                MonthCount(month, name, per_month[(year, month)], [WeekCount(w, n) for w, n in sorted(weeks.items())])
                for month, (name, weeks) in sorted(months.items())
            ],
        )
        for year, months in sorted(years.items(), reverse=True)
    ]


def _seeded(seed: int, sha256: str) -> str:
    return hashlib.sha256(f"{seed}:{sha256}".encode()).hexdigest()


def pick(ids: list[str], selection: Selection) -> list[str]:
    """The mode over the universe already filtered and ordered by sha256 (with `sha256s`, already only the asked
    ones). `pages`: those pages of `per_page`; `sample`: that many, by the hash of seed + sha256 (the same seed, the
    same sample) or at random without a seed, answered ordered by sha256."""
    if selection.pages is not None and selection.per_page is not None:
        start, end = selection.pages
        return ids[(start - 1) * selection.per_page : end * selection.per_page]
    if selection.sample is not None:
        if selection.seed is None:
            chosen = random.SystemRandom().sample(ids, min(selection.sample, len(ids)))
        else:
            seed = selection.seed
            chosen = sorted(ids, key=lambda sha256: _seeded(seed, sha256))[: selection.sample]
        return sorted(chosen)
    return ids


def month_pattern(month: int | None) -> str | None:
    """`mes` is stored as the corpus folder names it (11_Noviembre): its leading number, with or without a zero."""
    return None if month is None else f"0*{month}(\\D.*)?"


class DocumentSelection:
    def __init__(self, graph: GraphAdapter) -> None:
        self._graph = graph

    def experiment_exists(self, id: str) -> bool:
        return bool(self._graph.read(_EXPERIMENT, {"id": id}))

    def periods(self, universe: Universe, exclude: str | None) -> list[YearCount]:
        """The years, months and weeks (of their RAW) of the documents of a universe, with how many each has: what a
        selection's `year`, `month` and `week` can take. `exclude`: without the documents that experiment has."""
        return periods_of(self._graph.read(_UNIVERSES[universe] + _PERIODS, {"exclude": exclude}))

    def select(self, universe: Universe, selection: Selection, exclude: str | None) -> list[str]:
        """Every document of the selection, ordered by sha256."""
        parameters: Parameters = {
            "filtered": selection.filtered,
            "types": [t.lower() for t in selection.types],
            "year": selection.year,
            "month": selection.month,
            "month_pattern": month_pattern(selection.month),
            "week": selection.week,
            "sha256s": list(selection.sha256s),
            "exclude": exclude,
        }
        rows = self._graph.read(_UNIVERSES[universe] + _FILTERED, parameters)
        return pick([str(row["id"]) for row in rows], selection)
