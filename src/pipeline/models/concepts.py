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
FILE_BATCH = "lote_archivos"  # sha256s of ingesta, frozen by a selection
CONVERSION = "conversion"  # a chunking experiment that only converted
APPROVED_CONVERSION = "conversion_aprobada"
OFFICIAL_JSON = "json_oficial"  # sha256s of the official JSON nodes written by a promotion
JSON_BATCH = "lote_json"  # ids of official JSON nodes, frozen by a selection
CHUNKS = "chunks"  # a chunking experiment with a plan, from official JSON
APPROVED_CHUNKS = "chunks_aprobados"
OFFICIAL_CHUNKS = "chunks_oficiales"
EMBEDDINGS = "embeddings"
REVIEW = "revision"

# Approving a cycle turns what its stages gave into its approved version; the rest keep their name.
APPROVED: Mapping[str, str] = {CONVERSION: APPROVED_CONVERSION, CHUNKS: APPROVED_CHUNKS}


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
