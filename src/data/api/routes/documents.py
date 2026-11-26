"""POST /documents/search (feature 057): the chunked documents whose course matches the words of a text; POST
/documents/select (feature 062): the documents of a universe (parsed or chunked) that follow a selection. Read only.

consultas asks the first with the question, to search only the chunks of the course the question names; the pipeline
asks the second which documents it hands to chunking and embeddings (data chooses nothing: it answers)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from data.api.dependencies import Graph
from data.api.schemas import (
    NEO4J_DOWN,
    DocumentHit,
    DocumentSearch,
    DocumentSelect,
    FileSelection,
    SelectedDocuments,
    error,
)
from data.models import GraphRow
from data.repository.document_repository import DocumentRepository
from data.repository.document_selection import DocumentSelection, Universe, YearCount
from data.schema.selection_rules import Selection, selection_problem

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_K = 50
MAX_TEXT = 2000


def _repository(graph: Graph) -> DocumentRepository:
    return DocumentRepository(graph)


Documents = Annotated[DocumentRepository, Depends(_repository)]


def _text(row: GraphRow, key: str) -> str | None:
    value = row.get(key)
    return None if value is None else str(value)


def _hit(row: GraphRow) -> DocumentHit:
    score = row["score"]
    return DocumentHit(
        sha256=str(row["sha256"]),
        score=float(score) if isinstance(score, (int, float)) else 0.0,
        name=_text(row, "name"),
        activity_code=_text(row, "activity_code"),
        origin=_text(row, "origin"),
        code=_text(row, "code"),
    )


@router.post("/search", responses={422: error("k or text out of range"), 503: error(NEO4J_DOWN)})
def search(documents: Documents, body: DocumentSearch) -> list[DocumentHit]:
    """The chunked documents whose course (name or code, as embeddings read them from the PIAA's header) best match
    the words of `text`, best first (Lucene's score: only comparable within one answer). Empty if none matches or no
    document has its course yet (embedded before feature 057)."""
    if not 1 <= body.k <= MAX_K:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"k must be between 1 and {MAX_K}")
    if len(body.text) > MAX_TEXT:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"text can't have more than {MAX_TEXT} characters")
    return [_hit(row) for row in documents.search(body.text, body.k)]


def _selection(files: FileSelection) -> Selection:
    return Selection(
        all=files.all,
        sha256s=tuple(dict.fromkeys(files.sha256s)),
        pages=None if files.pages is None else (files.pages.start, files.pages.end),
        per_page=files.per_page,
        sample=files.sample,
        seed=files.seed,
        types=tuple(files.types),
        year=files.year,
        month=files.month,
        week=files.week,
    )


@router.post(
    "/select",
    responses={
        404: error("there is no chunking experiment with the id of exclude_experiment"),
        422: error(
            "the selection breaks a rule (exactly one mode, per_page only with pages...): the detail says which"
        ),
        503: error(NEO4J_DOWN),
    },
)
def select(graph: Graph, body: DocumentSelect) -> SelectedDocuments:
    """The documents of `universe` (`parsed`: JSON parseado or parcial; `chunked`: JSON fragmentado) that follow
    `files`, ordered by sha256: `all`; `sha256s` (only those of the universe); `pages` of `per_page` or a `sample` (with
    `seed` it repeats: ordered by the hash of seed + sha256), both after the filters (`types`, `year`, `month`, `week`:
    those of the document's RAW). `exclude_experiment`: without the documents that chunking experiment
    already has. The answer comes a page at a time (`page`, `per_page`); a sample without seed is drawn again on
    each request: ask for it in one page."""
    selection = _selection(body.files)
    problem = selection_problem(selection)
    if problem is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"files: {problem}")
    documents = DocumentSelection(graph)
    if body.exclude_experiment is not None and not documents.experiment_exists(body.exclude_experiment):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"there is no chunking experiment with id {body.exclude_experiment!r}"
        )
    found = documents.select(body.universe, selection, body.exclude_experiment)
    start = (body.page - 1) * body.per_page
    return SelectedDocuments(
        total=len(found), sha256s=found[start : start + body.per_page], pages=-(-len(found) // body.per_page)
    )


@router.get("/periods", responses={404: error("there is no chunking experiment with that id"), 503: error(NEO4J_DOWN)})
def periods(graph: Graph, universe: Universe = "parsed", exclude_experiment: str | None = None) -> list[YearCount]:
    """The years, months and weeks of the documents of `universe` (those of their RAW), the newest year first, with how
    many documents each has: what `year`, `month` (1-12, from `mes` 03_Marzo) and `week` (Semana_02) of a selection
    can take. `exclude_experiment`: without the documents that chunking experiment already has."""
    documents = DocumentSelection(graph)
    if exclude_experiment is not None and not documents.experiment_exists(exclude_experiment):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"there is no chunking experiment with id {exclude_experiment!r}"
        )
    return documents.periods(universe, exclude_experiment)
