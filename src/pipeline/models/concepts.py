"""What a pipeline is made of: templates, their stages and the things (artifacts) a stage needs and gives."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]


def json_list(values: Iterable[str]) -> list[JsonValue]:
    """Texts as a JSON list (a list[str] isn't a list[JsonValue] for mypy: lists are invariant)."""
    return [*values]


CYCLE = "cycle"  # the `action` of a cycle stage (it isn't in the catalog: it groups other stages)


class StageKind(StrEnum):
    TASK = "task"  # the pipeline does it, calling a module
    WAIT = "wait"  # an actor does it; the run waits for its answer
    CYCLE = "cycle"  # a group of stages repeated until its actor approves


# Artifacts: what a stage gives and the next ones need (stored names, in Spanish). An `external` stage may declare
# others: they are free text.
FILE_BATCH = "lote_archivos"  # sha256s of ingesta's chunkable files, frozen by a selection
RAW_FILES = "archivos_raw"  # an ingestion ran: the current files are RAW nodes in data (its id)
PARSED = "parseados"  # sha256s with a DoclingDocument in data (the already parsed and the just parsed)
CHUNKED = "chunkeados"  # sha256s chunked into the official graph with the active configuration
EMBEDDED = "embebidos"  # sha256s whose official chunks were embedded
CHUNKING_EXPERIMENT = "experimento_chunking"  # a chunking experiment over the batch (id)
EMBEDDINGS_EXPERIMENT = "experimento_embeddings"  # an embeddings experiment over a chunking experiment (id)
EMBEDDINGS_EXPERIMENTS = "experimentos_embeddings"  # feature 062: one embeddings experiment per model (ids, in order)
APPROVED_CHUNKING = "experimento_chunking_aprobado"
APPROVED_EMBEDDINGS = "experimento_embeddings_aprobado"
CHUNKING_APPLIED = "configuracion_chunking"  # the approved chunking configuration is now the active one
EMBEDDINGS_APPLIED = "configuracion_embeddings"
APPROVED_LLM = "llm_aprobado"  # the llm configuration of the approved laboratory iteration (feature 050), if it had one
LLM_APPLIED = "configuracion_llm"  # it is now llm's active configuration (None: the approved iteration had none)

# Approving a cycle turns what its stages gave into its approved version; the rest keep their name.
APPROVED: Mapping[str, str] = {CHUNKING_EXPERIMENT: APPROVED_CHUNKING, EMBEDDINGS_EXPERIMENT: APPROVED_EMBEDDINGS}


def approved(artifact: str) -> str:
    return APPROVED.get(artifact, artifact)


@dataclass(frozen=True)
class Stage:
    """A stage of a template. `id` is unique in the template (cycle steps included). A cycle (`action` = CYCLE) has
    its steps in `stages`, an `actor` who approves and an optional `max_iterations`. `needs`/`gives` are only read
    for `external` stages (the catalog declares those of the others)."""

    id: str
    action: str
    params: JsonObject = field(default_factory=dict)
    actor: str | None = None
    stages: tuple[Stage, ...] = ()
    max_iterations: int | None = None
    needs: tuple[str, ...] = ()
    gives: tuple[str, ...] = ()

    @property
    def is_cycle(self) -> bool:
        return self.action == CYCLE


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    description: str
    stages: tuple[Stage, ...]
    builtin: bool = False  # the default template: it can be edited but not deleted
    created: str = ""
    modified: str = ""


@dataclass(frozen=True)
class Actor:
    """Someone the pipeline waits for. With `callback_url`, it is told (POST) when a stage starts waiting for it."""

    name: str
    callback_url: str | None = None
