"""What is asked: a question, alone (search) or to be answered (ask), maybe with attachments (phase 2: documents and
images that search what is similar to them), and a comparison of up to four panels (feature 060)."""

from dataclasses import dataclass, field

from .concepts import Attachment, LlmOptions


@dataclass(frozen=True)
class Against:
    """Where a question searches, instead of the official chunks with the active model: exactly one of them.

    `embeddings_experiment`: the EXP_CHUNK of an embeddings experiment (the laboratory, feature 053); nothing is kept
    as official: the question is marked `laboratorio`.
    `embeddings_model` (feature 060): the official chunks with another embeddings model than the active one (its own
    vectors and index); an official question."""

    embeddings_experiment: str | None = None
    embeddings_model: str | None = None

    @property
    def laboratory(self) -> bool:
        return self.embeddings_experiment is not None


@dataclass(frozen=True)
class Question:
    text: str  # empty only with attachments: then ATTACHMENT_QUESTION is asked
    k: int | None = None  # None: the active configuration's
    chat: str | None = None  # None: a new chat
    llm: LlmOptions = field(default_factory=LlmOptions)
    against: Against | None = None
    attachments: tuple[Attachment, ...] = ()

    @property
    def laboratory(self) -> bool:
        return self.against is not None and self.against.laboratory


@dataclass(frozen=True)
class Panel:
    """One panel of a comparison (feature 060): where it searches, with which LLM and how many chunks."""

    label: str
    against: Against | None = None
    llm: LlmOptions = field(default_factory=LlmOptions)
    k: int | None = None


@dataclass(frozen=True)
class ComparisonRequest:
    text: str  # empty only with attachments
    panels: tuple[Panel, ...]  # 1 to MAX_PANELS, in the order they run
    attachments: tuple[Attachment, ...] = ()
