"""What chunking is asked to do (features 043, 045 and 059): an experiment over some parsed documents (or all of
them), and a run of the official chunking with the active configuration over some documents or over a page of what
is missing."""

from dataclasses import dataclass, field

from .concepts import ChunkingParameters


@dataclass(frozen=True)
class ExperimentRequest:
    name: str
    description: str
    parameters: ChunkingParameters
    sha256s: list[str] = field(default_factory=list)  # exactly these (repeated ones once)
    from_experiment: str | None = None  # or the documents of another experiment
    all: bool = False  # or every parsed JSON data has when its turn comes (feature 059)


@dataclass(frozen=True)
class RunRequest:
    """Exactly these sha256s, or (empty) what is missing with the active configuration: one page of it, or all."""

    sha256s: list[str] = field(default_factory=list)
    page: int | None = None
    per_page: int | None = None
    simulate: bool = False  # only count what would be chunked and skipped
