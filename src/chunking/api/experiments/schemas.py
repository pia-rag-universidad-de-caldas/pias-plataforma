"""Bodies of the experiment routes (feature 043)."""

from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import Field, JsonValue

from chunking.api.schemas import STRICT, ChunkingBody, Sha256
from chunking.models import ConfigValue, ExperimentProgress, ExperimentSelection, ExperimentStatus


@dataclass(frozen=True)
class NewExperiment:
    """Exactly one of `sha256s` (documents already parsed), `from_experiment` (the documents of another one) and
    `all` (every parsed JSON data has when its turn comes, feature 059)."""

    __pydantic_config__ = STRICT

    name: Annotated[str, Field(min_length=1)]
    sha256s: list[Sha256] = field(default_factory=list)
    from_experiment: str | None = None
    all: bool = False
    description: str = ""
    chunking: ChunkingBody = field(default_factory=ChunkingBody)
    simulate: bool = False  # only which documents would enter and which aren't parsed


@dataclass(frozen=True)
class ExperimentStarted:
    id: str | None  # None with simulate
    status: Literal["queued", "running", "simulated"]
    documents: list[str]  # the sha256s that enter; with `all`, empty: they are taken when its turn comes
    unparsed: list[str]  # those without a parse (sin_parseo): they don't enter
    chunking: dict[str, ConfigValue]  # the resolved configurable part
    all: bool = False  # every parsed JSON (feature 059)
    total: int = 0  # how many enter: len(documents), or with `all` the parsed JSON there are now


@dataclass(frozen=True)
class ExperimentSummary:
    id: str
    name: str
    description: str
    status: ExperimentStatus
    created: str
    finished: str | None
    progress: ExperimentProgress
    all: bool = False  # it took every parsed JSON (feature 059)


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
    all: bool = False  # it took every parsed JSON (feature 059)
    selections: list[ExperimentSelection] = field(default_factory=list)  # when documents entered (feature 062)


@dataclass(frozen=True)
class NewDocuments:
    """Body of POST /experiments/{id}/documents (feature 062): parsed documents to add to its list."""

    __pydantic_config__ = STRICT

    sha256s: Annotated[list[Sha256], Field(min_length=1)]
    simulate: bool = False  # only which would enter


@dataclass(frozen=True)
class DocumentsAdded:
    id: str
    status: Literal["queued", "running", "simulated"]
    added: list[str]  # new and parsed: they enter its list and are chunked with its configuration
    already: list[str]  # it had them
    unparsed: list[str]  # new but without a parse: they don't enter
    total: int  # documents in its list now (with simulate, what it would have)
