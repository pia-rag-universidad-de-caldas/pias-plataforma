"""What is asked: a question, alone (search) or to be answered (ask), maybe with attachments (phase 2: documents and
images that search what is similar to them)."""

from dataclasses import dataclass, field

from .concepts import Attachment, LlmOptions


@dataclass(frozen=True)
class Against:
    """Ask the laboratory instead of the official chunks (feature 053): the EXP_CHUNK of an embeddings experiment.
    Nothing is kept as official: the question is marked `laboratorio`."""

    embeddings_experiment: str


@dataclass(frozen=True)
class Question:
    text: str  # empty only with attachments: then ATTACHMENT_QUESTION is asked
    k: int | None = None  # None: the active configuration's
    chat: str | None = None  # None: a new chat
    llm: LlmOptions = field(default_factory=LlmOptions)
    against: Against | None = None
    attachments: tuple[Attachment, ...] = ()
