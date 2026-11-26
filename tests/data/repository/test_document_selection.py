"""DocumentSelection (feature 062): the mode over the filtered universe (pick, without Neo4j) and the filters and the
exclusion of an experiment's documents against a real Neo4j (`neo4j`)."""

import re

import pytest

from data.models import GraphAdapter, GraphRow
from data.repository.document_selection import DocumentSelection, month_number, month_pattern, periods_of, pick
from data.schema.selection_rules import Selection

IDS = [f"{n:02d}" for n in range(10)]


def test_pages_take_those_pages_of_per_page() -> None:
    assert pick(IDS, Selection(pages=(2, 3), per_page=3)) == ["03", "04", "05", "06", "07", "08"]


def test_a_sample_with_a_seed_repeats_and_comes_ordered() -> None:
    first = pick(IDS, Selection(sample=4, seed=7))
    assert first == pick(IDS, Selection(sample=4, seed=7)) and first == sorted(first) and len(first) == 4


def test_another_seed_gives_another_sample() -> None:
    samples = {tuple(pick(IDS, Selection(sample=4, seed=seed))) for seed in range(5)}
    assert len(samples) > 1


def test_a_sample_without_seed_takes_that_many_of_the_universe() -> None:
    chosen = pick(IDS, Selection(sample=3))
    assert len(chosen) == 3 and set(chosen) <= set(IDS)


def test_a_sample_larger_than_the_universe_takes_all_of_it() -> None:
    assert pick(IDS, Selection(sample=50)) == IDS


def test_all_and_sha256s_take_what_the_query_answered() -> None:
    assert pick(IDS, Selection(all=True)) == IDS


@pytest.mark.parametrize(
    ("month", "stored", "matches"), [(3, "03_Marzo", True), (3, "3_Marzo", True), (3, "13_X", False)]
)
def test_the_month_is_the_leading_number_of_mes(month: int, stored: str, matches: bool) -> None:
    assert bool(re.fullmatch(month_pattern(month) or "", stored)) is matches


@pytest.mark.neo4j
def test_the_filters_and_the_exclusion_against_neo4j(real_graph: GraphAdapter, test_prefix: str) -> None:
    real_graph.write(
        """
        CREATE (a:JSON {id: $p + 'a', estado: 'parseado', estado_chunking: 'fragmentado'})
        CREATE (b:JSON {id: $p + 'b', estado: 'parcial'})
        CREATE (c:JSON {id: $p + 'c', estado: 'parseado'})
        CREATE (:JSON {id: $p + 'd', estado: 'error'})
        CREATE (a)-[:VIENE_DE]->(:RAW {id: $p + 'a', tipo: 'pdf', anio: 2024, mes: '03_Marzo', semana: 'Semana_01'})
        CREATE (b)-[:VIENE_DE]->(:RAW {id: $p + 'b', tipo: 'docx', anio: 2024, mes: '03_Marzo'})
        CREATE (c)-[:VIENE_DE]->(:RAW {id: $p + 'c', tipo: 'pdf', anio: 2023, mes: '11_Noviembre'})
        CREATE (e:EXPERIMENTO {id: $p + 'exp'})-[:EXP_TIENE_DOCUMENTO]->(x:EXP_DOCUMENTO {id: $p + 'exp:a'})
        CREATE (x)-[:EXP_DE]->(a)
        """,
        {"p": test_prefix},
    )
    documents = DocumentSelection(real_graph)

    def mine(universe: str, selection: Selection, exclude: str | None = None) -> list[str]:  # only this test's
        found = documents.select("chunked" if universe == "chunked" else "parsed", selection, exclude)
        return [id for id in found if id.startswith(test_prefix)]

    assert mine("parsed", Selection(all=True)) == [f"{test_prefix}{x}" for x in "abc"]
    assert mine("chunked", Selection(all=True)) == [f"{test_prefix}a"]
    assert mine("parsed", Selection(all=True, types=("PDF",))) == [f"{test_prefix}a", f"{test_prefix}c"]
    march = Selection(all=True, year=2024, month=3)
    assert mine("parsed", march) == [f"{test_prefix}a", f"{test_prefix}b"]
    assert mine("parsed", march, f"{test_prefix}exp") == [f"{test_prefix}b"]
    years = {y.year: y for y in documents.periods("parsed", f"{test_prefix}exp")}  # with the rest of the graph
    assert any(m.month == 3 and m.documents >= 1 for m in years[2024].months)
    asked = Selection(sha256s=(f"{test_prefix}c", f"{test_prefix}d"))
    assert documents.select("parsed", asked, None) == [f"{test_prefix}c"]
    assert documents.experiment_exists(f"{test_prefix}exp") and not documents.experiment_exists(f"{test_prefix}no")


@pytest.mark.parametrize(("stored", "number"), [("03_Marzo", 3), ("11_Noviembre", 11), ("13_X", None), ("Marzo", None)])
def test_month_number_is_the_leading_number_of_mes(stored: str, number: int | None) -> None:
    assert month_number(stored) == number


def test_periods_group_years_months_and_weeks_with_their_documents() -> None:
    rows: list[GraphRow] = [
        {"year": 2024, "month": "03_Marzo", "week": "Semana_02", "documents": 2},
        {"year": 2024, "month": "03_Marzo", "week": "Semana_01", "documents": 1},
        {"year": 2024, "month": "11_Noviembre", "week": None, "documents": 4},
        {"year": 2023, "month": None, "week": None, "documents": 5},
    ]
    found = periods_of(rows)
    assert [(y.year, y.documents) for y in found] == [(2024, 7), (2023, 5)]
    march = found[0].months[0]
    assert (march.month, march.name, march.documents, [(w.week, w.documents) for w in march.weeks]) == (
        3,
        "03_Marzo",
        3,
        [("Semana_01", 1), ("Semana_02", 2)],
    )
    assert (found[0].months[1].weeks, found[1].months) == ([], [])


def test_rows_without_a_year_are_left_out() -> None:
    assert periods_of([{"year": None, "month": "03_Marzo", "week": None, "documents": 3}]) == []
