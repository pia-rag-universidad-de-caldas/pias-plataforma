"""What is asked for: the documents whoever calls chooses (the pipeline), or what is missing (feature 057)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RunRequest:
    """Production: these chunked documents, with the active configuration (read when the run is queued). Without
    sha256s, the chunked documents missing that model's vectors (as data counts them when the run's turn comes): one
    page of them (`page`, `per_page`) or all."""

    sha256s: list[str]  # empty: what is missing
    simulate: bool = False
    force: bool = False  # embed again even what didn't change
    model: str | None = None  # another served model, next to the active one (feature 055); None: the active one
    page: int | None = None  # of what is missing, when sha256s is empty
    per_page: int | None = None


@dataclass(frozen=True)
class ExperimentRequest:
    """Laboratory: the chunks of a finished chunking experiment, with a model and a limit to try."""

    chunking_experiment: str  # id of the chunking EXPERIMENTO
    model: str
    max_tokens: int | None = None  # None: the model's default_tokens
    name: str = ""
    description: str = ""
    simulate: bool = False
