"""What chunking reads back to answer (feature 043): experiments, as stored, and their comparison."""

from dataclasses import dataclass

from .concepts import ChunkingParameters
from .results import ExperimentProgress, ExperimentResults, ExperimentStatus


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


@dataclass(frozen=True)
class DocumentUse:
    """An EXP_USA as read: what an experiment did with one document (feature 045, to resume it)."""

    sha256: str
    chunked: bool  # estado fragmentado
    chunks: int
    tokens: list[int]  # of each chunk; empty if it was stored before feature 045
