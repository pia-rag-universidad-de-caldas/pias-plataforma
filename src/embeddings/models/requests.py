"""What is asked for. Never "everything" nor a number of documents: whoever calls (the pipeline) chooses which."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RunRequest:
    """Production: these chunked documents, with the active configuration (read when the run is queued)."""

    sha256s: list[str]  # never empty: the API refuses an empty list
    simulate: bool = False
    force: bool = False  # embed again even what didn't change
    model: str | None = None  # another served model, next to the active one (feature 055); None: the active one


@dataclass(frozen=True)
class ExperimentRequest:
    """Laboratory: the chunks of a finished chunking experiment, with a model and a limit to try."""

    chunking_experiment: str  # id of the chunking EXPERIMENTO
    model: str
    max_tokens: int | None = None  # None: the model's default_tokens
    name: str = ""
    description: str = ""
    simulate: bool = False
