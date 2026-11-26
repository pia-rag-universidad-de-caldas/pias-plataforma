"""What chunking reads back to answer (feature 043): experiments, as stored, and their comparison."""

from dataclasses import dataclass, field

from .concepts import ChunkingParameters
from .results import ExperimentProgress, ExperimentResults, ExperimentStatus


@dataclass(frozen=True)
class ExperimentSelection:
    """One time documents entered an experiment (feature 062): when it was created, or a POST .../documents."""

    at: str  # ISO
    kind: str  # created or added
    documents: int  # how many entered then


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
    documents_json: str  # the sha256s (or from_experiment) asked for
    chunking_json: str  # the resolved parameters
    results_json: str | None
    error: str | None
    results: ExperimentResults | None = None  # results_json, parsed
    started: str | None = None  # when its turn came
    parameters: ChunkingParameters | None = None  # chunking_json, parsed
    all: bool = False  # it took every parsed JSON (feature 059): documents_json says "all": true
    selections: list[ExperimentSelection] = field(default_factory=list)  # feature 062; one of before: none stored


@dataclass(frozen=True)
class DocumentUse:
    """An EXP_DOCUMENTO as read: what an experiment did with one document (feature 045, to resume it)."""

    sha256: str
    chunked: bool  # estado fragmentado
    chunks: int
    tokens: list[int]  # of each chunk; empty if it was stored before feature 045


@dataclass(frozen=True)
class ExperimentDependents:
    """What uses an experiment (feature 055 part b): deleting it would leave them pointing at nothing."""

    embeddings: list[str]  # ids of the EXP_EMBEDDINGS over its chunks (EXP_USA)
    pipeline: list[str]  # ids of the PIPE_ITERACION that link it (PIPE_USA)

    @property
    def any(self) -> bool:
        return bool(self.embeddings or self.pipeline)
