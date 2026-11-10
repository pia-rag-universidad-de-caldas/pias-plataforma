"""Bodies of the experiment routes (feature 043)."""

from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import Field, JsonValue

from chunking.api.schemas import STRICT, ChunkingBody, Sha256
from chunking.models import ExperimentProgress, ExperimentStatus


@dataclass(frozen=True)
class NewExperiment:
    """Exactly one of `sha256s` (documents already parsed) and `from_experiment` (the documents of another one)."""

    __pydantic_config__ = STRICT

    name: Annotated[str, Field(min_length=1)]
    sha256s: list[Sha256] = field(default_factory=list)
    from_experiment: str | None = None
    description: str = ""
    chunking: ChunkingBody = field(default_factory=ChunkingBody)
    simulate: bool = False  # only which documents would enter and which aren't parsed


@dataclass(frozen=True)
class ExperimentStarted:
    id: str | None  # None with simulate
    status: Literal["queued", "running", "simulated"]
    documents: list[str]  # the sha256s that enter
    unparsed: list[str]  # those without a parse (sin_parseo): they don't enter
    chunking: dict[str, str | int | bool]  # the resolved configurable part


@dataclass(frozen=True)
class ExperimentSummary:
    id: str
    name: str
    description: str
    status: ExperimentStatus
    created: str
    finished: str | None
    progress: ExperimentProgress


@dataclass(frozen=True)
class ExperimentView:
    id: str
    name: str
    description: str
    status: ExperimentStatus
    created: str
    started: str | None
    finished: str | None
    progress: ExperimentProgress
    documents: JsonValue  # what was asked for
    chunking: JsonValue  # the parameters it chunked with
    chunked: list[str]  # the sha256s chunked (what the pipeline hands to embeddings)
    results: JsonValue
    error: str | None
