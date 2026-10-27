"""What chunking reads back to answer: production documents (GET /chunking/documents) and experiments, their
documents and sections, and their comparison (read from the graph through data)."""

from dataclasses import dataclass

from .concepts import Chunk, DocumentStatus, ProcessedDocument, Score, Section
from .results import ExperimentProgress, ExperimentResults, ExperimentStatus, TokenStats


@dataclass(frozen=True)
class DocumentPage:
    page: int
    per_page: int
    total: int  # documents in the graph, across all pages
    pages: int
    documents: list[ProcessedDocument]


@dataclass(frozen=True)
class DocumentChunks:
    """A document with its sections and its chunks, in order."""

    document: ProcessedDocument
    sections: list[Section]
    chunks: list[Chunk]


@dataclass(frozen=True)
class ExperimentRecord:
    """An EXPERIMENTO as read from the graph. The request and the results are kept as the JSON stored."""

    id: str
    name: str
    description: str
    status: ExperimentStatus
    created: str
    finished: str | None
    progress: ExperimentProgress
    files_json: str  # the `files` asked for
    conversion_json: str
    plan_json: str
    results_json: str | None
    error: str | None
    results: "ExperimentResults | None" = None  # results_json, parsed


@dataclass(frozen=True)
class ExperimentDocument:
    """A document of an experiment (what the EXP_USA relationship records)."""

    sha256: str
    conversion_id: str  # id of its EXP_DOCUMENTO: <sha256>:<conversion fingerprint>
    origin: str | None
    name: str | None
    code: str | None
    reused: bool
    status: DocumentStatus
    error: str | None
    sections: int
    chunks: int


@dataclass(frozen=True)
class ExperimentSection:
    """An EXP_SECCION: how one section of a document was treated in one experiment."""

    index: int
    title: str
    level: int
    pages: list[int]
    rule: int | None  # index of the rule that took it; None = the plan's default
    strategy: str
    parameters_json: str
    chunks: int
    tokens: int


@dataclass(frozen=True)
class ScoreSummary:
    count: int
    averages: dict[str, float | None]  # per criterion (the config test ones always, None without values)
    overall: float | None  # average of every value of every score


@dataclass(frozen=True)
class KeyResults:
    """The numbers of `resultados` worth comparing."""

    documents: int
    converted: int
    reused: int
    errors: int
    sections: int
    chunks: int
    tokens: TokenStats | None  # across every chunk of the experiment


@dataclass(frozen=True)
class ComparedExperiment:
    id: str
    name: str
    status: ExperimentStatus
    conversion_json: str
    plan_json: str
    scores: list[Score]
    summary: ScoreSummary
    results: KeyResults | None  # None while it runs
