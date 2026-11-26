"""POST /documents/search (feature 057): the documents of the courses a text names."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from data.models import GraphRow
from data.repository.document_repository import lucene_words

DataClient = Callable[..., TestClient]
ROW: GraphRow = {
    "sha256": "a",
    "score": 4.5,
    "name": "PSICOLOGÍA DE LA PERCEPCIÓN",
    "activity_code": "0100105",
    "origin": "2020/x.pdf",
    "code": "000944",
}


def test_a_search_answers_the_documents_with_their_course(data_client: DataClient) -> None:
    answer = data_client([ROW]).post("/documents/search", json={"text": "psicología de la percepción"})
    assert answer.status_code == 200 and answer.json() == [{**ROW, "score": 4.5}]


@pytest.mark.parametrize("body", [{"text": "x", "k": 0}, {"text": "x" * 2001}])
def test_out_of_range_is_422(data_client: DataClient, body: dict[str, object]) -> None:
    assert data_client().post("/documents/search", json=body).status_code == 422


def test_only_words_reach_lucene() -> None:
    assert lucene_words('¿qué evalúa "Cálculo" AND title:x*?') == "qué evalúa Cálculo AND title x"


SELECTED: list[GraphRow] = [{"id": f"{n:02d}"} for n in range(5)]


def test_a_selection_answers_a_page_of_its_documents(data_client: DataClient) -> None:
    body = {"universe": "parsed", "files": {"all": True}, "per_page": 2, "page": 2}
    answer = data_client(SELECTED).post("/documents/select", json=body)
    assert answer.status_code == 200 and answer.json() == {"total": 5, "sha256s": ["02", "03"], "pages": 3}


def test_pages_of_files_go_over_the_filtered_universe(data_client: DataClient) -> None:
    files = {"pages": {"from": 2, "to": 2}, "per_page": 2, "types": ["pdf"]}
    answer = data_client(SELECTED).post("/documents/select", json={"universe": "chunked", "files": files})
    assert answer.json() == {"total": 2, "sha256s": ["02", "03"], "pages": 1}


@pytest.mark.parametrize(
    "files",
    [
        {"all": True, "sample": 3},
        {"pages": {"from": 1, "to": 1}},
        {"sha256s": ["a"], "year": 2024},
        {"all": True, "week": "Semana_01"},
        {"all": True, "extra": 1},
        {"all": True, "code": "000944"},
    ],
)
def test_a_selection_that_breaks_a_rule_is_422(data_client: DataClient, files: dict[str, object]) -> None:
    answer = data_client(SELECTED).post("/documents/select", json={"universe": "parsed", "files": files})
    assert answer.status_code == 422


def test_excluding_an_experiment_that_isnt_there_is_404(data_client: DataClient) -> None:
    body = {"universe": "parsed", "files": {"all": True}, "exclude_experiment": "nope"}
    assert data_client([]).post("/documents/select", json=body).status_code == 404


def test_excluding_an_experiment_selects_after_checking_it(data_client: DataClient) -> None:
    body = {"universe": "parsed", "files": {"all": True}, "exclude_experiment": "exp"}
    answer = data_client([{"id": "exp"}], SELECTED[:1]).post("/documents/select", json=body)
    assert answer.json() == {"total": 1, "sha256s": ["00"], "pages": 1}


def test_periods_answer_years_months_and_weeks(data_client: DataClient) -> None:
    rows: list[GraphRow] = [{"year": 2024, "month": "03_Marzo", "week": "Semana_01", "documents": 2}]
    answer = data_client(rows).get("/documents/periods", params={"universe": "chunked"})
    assert answer.json() == [
        {
            "year": 2024,
            "documents": 2,
            "months": [
                {"month": 3, "name": "03_Marzo", "documents": 2, "weeks": [{"week": "Semana_01", "documents": 2}]}
            ],
        }
    ]


def test_periods_without_an_experiment_that_isnt_there_is_404(data_client: DataClient) -> None:
    assert data_client([]).get("/documents/periods", params={"exclude_experiment": "nope"}).status_code == 404
