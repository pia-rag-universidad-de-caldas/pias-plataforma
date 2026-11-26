"""Bodies of the requests and answers (keys in English, like data and chunking). A response that already is an
embeddings.models model (EmbeddingRun) is used as it is. An unknown key is a 422, never ignored."""

from dataclasses import dataclass, field, fields
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from embeddings.config import MAX_PER_PAGE, MAX_TEXT, MAX_TEXTS, MODELS
from embeddings.models import ConfigOrigin, EmbeddingRun

STRICT = ConfigDict(extra="forbid")
type Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]  # lowercase hex, as ingesta stores it
type Limit = Annotated[int, Field(ge=1)]  # the ceiling depends on the model: domain/limits.py
type ServiceState = Literal["ok", "unavailable"]


@dataclass(frozen=True)
class HealthStatus:
    status: Literal["ok", "degraded"]  # ok if torch and transformers are installed and data answers
    version: str
    models: Literal["installed", "missing"]  # the `embed` extra (no model is loaded to answer)
    data: ServiceState


@dataclass(frozen=True)
class ServedModel:
    """A model of config.MODELS; both limits count its special tokens."""

    name: str
    dimensions: int
    default_tokens: int
    max_tokens: int
    default: bool  # the one of the default configuration
    documents: int | None = None  # official documents with its vectors (feature 055); None if data doesn't answer
    vector_property: str = ""  # embedding_<model>_<dim>: GET /data/progress/embeddings?property= (feature 057)
    # Feature 062: the most tokens of the model's own tokenizer a chunk may have (chunking's `fit`), once its 2 special
    # tokens and its passage prefix are taken out; None if the prefix can't be counted (no `embed` extra).
    passage_budget: int | None = None  # over max_tokens
    default_passage_budget: int | None = None  # over default_tokens
    official_passage_budget: int | None = None  # over default_tokens, leaving room for the course in front (057)


@dataclass(frozen=True)
class NewRun:
    """Body of POST /runs: these chunked documents (repeated ones once), or what is missing with the model (one page
    of it, `page` and `per_page`, or all: feature 057), with the active configuration."""

    __pydantic_config__ = STRICT

    sha256s: list[Sha256] = field(default_factory=list)  # empty: what data says is missing when its turn comes
    page: Annotated[int | None, Field(ge=1)] = None
    per_page: Annotated[int | None, Field(ge=1, le=MAX_PER_PAGE)] = None
    force: bool = False  # embed again even what didn't change
    simulate: bool = False  # only say what it would do: nothing is calculated nor written
    model: str | None = None  # another served model, next to the active one (feature 055); then PUT /config


@dataclass(frozen=True)
class NewExperiment:
    """Body of POST /experiments: the chunks of a finished chunking experiment, with a model and a limit to try."""

    __pydantic_config__ = STRICT

    chunking_experiment: Annotated[str, Field(min_length=1)]
    model: str
    max_tokens: Limit | None = None  # None: the model's default_tokens
    name: str = ""
    description: str = ""
    simulate: bool = False


@dataclass(frozen=True)
class ExperimentResume:
    """Body of POST /experiments/{id}/resume (feature 062), optional: without sha256s, everything it is missing."""

    __pydantic_config__ = STRICT

    sha256s: list[Sha256] = field(default_factory=list)  # only these of what it is missing


@dataclass(frozen=True)
class ConfigBody:
    """Body of PUT /config: what is left out takes the model's default."""

    __pydantic_config__ = STRICT

    model: str
    max_tokens: Limit | None = None


@dataclass(frozen=True)
class ConfigPatch:
    """Body of PATCH /config: only what comes changes. Another model without max_tokens takes its default."""

    __pydantic_config__ = STRICT

    model: str | None = None
    max_tokens: Limit | None = None


@dataclass(frozen=True)
class DefaultConfig:
    model: str
    max_tokens: int


@dataclass(frozen=True)
class ConfigView:
    model: str
    max_tokens: int
    origin: ConfigOrigin
    experiment: str | None
    modified: str | None
    problem: str | None  # why the stored one isn't used (its model is no longer served, its limit doesn't fit)
    default: DefaultConfig
    vector_property: str = ""  # of its model: GET /data/progress/embeddings?property= says what is missing (057)


@dataclass(frozen=True)
class NewVectors:
    """Body of POST /vectors (feature 048): texts embedded with the active configuration's model."""

    __pydantic_config__ = STRICT

    texts: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=MAX_TEXT)]], Field(min_length=1, max_length=MAX_TEXTS)
    ]
    model: str | None = None  # another served model only for these texts (a question to an embeddings experiment)
    max_tokens: Limit | None = None  # None: the active one (or, with another model, that model's default)


@dataclass(frozen=True)
class TextVectors:
    """The vectors, in the order of the texts, and the indexes of the model that calculated them."""

    model: str
    max_tokens: int
    dimensions: int
    index: str  # the FRAGMENTOS index of that model (the official chunks)
    experiment_index: str  # the EXP_EMBED one (the vectors of embeddings experiments, feature 055)
    vectors: list[list[float]]


@dataclass(frozen=True)
class ExperimentView(EmbeddingRun):
    """An experiment as GET /experiments[/{id}] answers it (feature 059): everything of its EmbeddingRun, as before,
    and on top what the front shows to choose among the experiments over one chunking experiment."""

    model: str = ""  # config.model
    dimensions: int = 0  # of the model's vectors; 0 if the model is no longer served
    max_tokens: int = 0  # config.max_tokens
    documents: int = 0  # documents with vectors (progress.embedded)
    chunks: int = 0  # vectors calculated (progress.chunks)
    pending: int | None = None  # feature 062, only GET /experiments/{id}: chunked documents still without its vectors

    @staticmethod
    def of(run: EmbeddingRun, pending: int | None = None) -> "ExperimentView":
        spec = MODELS.get(run.config.model)
        return ExperimentView(
            **{f.name: getattr(run, f.name) for f in fields(EmbeddingRun)},
            model=run.config.model,
            dimensions=spec.dimensions if spec else 0,
            max_tokens=run.config.max_tokens,
            documents=run.progress.embedded,
            chunks=run.progress.chunks,
            pending=pending,
        )
