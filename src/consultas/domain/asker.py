"""Asker: a question → its vector (embeddings) → the closest chunks (data) → the answer (llm) → the chat (data).

It always cites: the answer comes with the chunks it was given as context. If no chunk passes min_score, it answers
that it found nothing and never calls the LLM. A module that doesn't answer stops it before anything is stored: the
question, its answer and its citations are one batch, written last.

With attachments (phase 2), each one searches too: a document by its pieces (parsing reads it, nothing is stored), an
image by what a vision model of llm sees in it; every search is joined by best score. The CONSULTA keeps their names
and types, never the files."""

import base64
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from common.clock import now
from consultas.config import ATTACHMENT_QUESTION, DESCRIBE_PROMPT, FINISHED_EXPERIMENT, MAX_TEXTS, NOT_FOUND
from consultas.models import (
    Against,
    Answer,
    Attachment,
    AttachmentKind,
    AttachmentUse,
    ChatStore,
    ChatSummary,
    ConfigStore,
    Conflict,
    Generator,
    InvalidQuestion,
    LlmModel,
    LlmOptions,
    Message,
    NotFound,
    Previewer,
    Question,
    QuestionProperties,
    QuestionVector,
    Retriever,
    Role,
    Seconds,
    Source,
    Vectors,
    Vision,
)

from .active_config import resolve
from .attachments import budgets, check, merged, pieces, spread, vision_model
from .prompt import messages, with_attachments
from .records import question_batch


def _new_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class Found:
    """What a search found, and with what."""

    vector: QuestionVector
    sources: list[Source]
    experiment: str | None  # the embeddings experiment searched (laboratory)
    attachments: list[AttachmentUse] = field(default_factory=list)
    images: tuple[str, ...] = ()  # base64 of the attached images: the final LLM sees them if it can
    models: list[LlmModel] = field(default_factory=list)  # what llm said of its models, if it was asked


def _b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


@dataclass(frozen=True)
class _Read:
    """An attachment turned into the texts it searches with."""

    use: AttachmentUse
    texts: list[str]


@dataclass
class Asker:
    vectors: Vectors
    retriever: Retriever
    generator: Generator
    chats: ChatStore
    config: ConfigStore
    previewer: Previewer | None = None  # parsing: without it a document can't be attached
    vision: Vision | None = None  # llm's models: without it an image can't be attached
    clock: Callable[[], float] = time.monotonic
    new_id: Callable[[], str] = _new_id
    today: Callable[[], str] = field(default=now)

    def _vector(self, text: str, against: Against | None) -> tuple[QuestionVector, str, str | None]:
        """The vector of the question, the index to search and the experiment to filter by."""
        if against is None:
            vector = self.vectors.question(text)
            return vector, vector.index, None
        experiment = self.vectors.experiment(against.embeddings_experiment)
        if experiment is None:
            raise NotFound(f"embeddings has no experiment {against.embeddings_experiment!r}")
        if experiment.status != FINISHED_EXPERIMENT:
            raise Conflict(f"the embeddings experiment {experiment.id!r} is {experiment.status}, not finished")
        vector = self.vectors.question(text, experiment.model, experiment.max_tokens)
        return vector, vector.experiment_index, experiment.id

    def search(
        self,
        text: str,
        k: int | None = None,
        against: Against | None = None,
        attachments: Sequence[Attachment] = (),
    ) -> Found:
        """The chunks closest to the question (and to its attachments), best first, without the final LLM and without
        min_score: what was found."""
        wanted = k if k is not None else resolve(self.config).k
        if not text.strip() and not attachments:
            raise InvalidQuestion("a question needs its text or some attachment")
        if not attachments:
            vector, index, experiment = self._vector(text, against)
            return Found(vector, self.retriever.search(index, vector.vector, wanted, experiment), experiment)
        kinds = check(attachments)
        images = [a for a, kind in zip(attachments, kinds, strict=True) if kind is AttachmentKind.IMAGE]
        models = self._models() if images else []
        descriptions = {a.name: self._describe(a, models) for a in images}
        vector, index, experiment = self._vector(text if text.strip() else ATTACHMENT_QUESTION, against)
        read = [
            self._read(attachment, kind, budget, vector.max_tokens, descriptions.get(attachment.name))
            for attachment, kind, budget in zip(attachments, kinds, budgets(kinds), strict=True)
        ]
        texts = [piece for r in read for piece in r.texts]
        searches = [self.retriever.search(index, vector.vector, wanted, experiment)] if text.strip() else []
        for start in range(0, len(texts), MAX_TEXTS):
            found = self.vectors.texts(texts[start : start + MAX_TEXTS], vector.model, vector.max_tokens)
            searches += [self.retriever.search(index, v, wanted, experiment) for v in found.vectors]
        sent = tuple(_b64(a.content) for a in images)
        return Found(vector, merged(searches, wanted), experiment, [r.use for r in read], sent, models)

    def _models(self) -> list[LlmModel]:
        if self.vision is None:
            raise InvalidQuestion("images can't be attached here: consultas has no access to llm's models")
        return self.vision.models()

    def _describe(self, image: Attachment, models: Sequence[LlmModel]) -> str:
        """What a vision model of llm sees in the image, in Spanish: the text that searches for it."""
        model = vision_model(models)
        message = Message(Role.USER, DESCRIBE_PROMPT, (_b64(image.content),))
        described = " ".join(self.generator.chat([message], LlmOptions(model=model)).content.split())
        if not described:
            raise InvalidQuestion(f"the vision model {model} described nothing in {image.name!r}")
        return described

    def _read(
        self, attachment: Attachment, kind: AttachmentKind, budget: int, max_tokens: int, description: str | None
    ) -> _Read:
        if kind is AttachmentKind.IMAGE:
            seen = description or ""
            use = AttachmentUse(attachment.name, attachment.mime, kind, 1, len(seen), description=seen)
            return _Read(use, [seen])
        if self.previewer is None:
            raise InvalidQuestion("documents can't be attached here: consultas has no access to parsing")
        document = self.previewer.preview(attachment.name, attachment.mime, attachment.content)
        found = pieces(document.sections, max_tokens)
        if not found:
            raise InvalidQuestion(f"parsing found no text in {attachment.name!r}")
        texts = spread(found, budget)
        truncated = document.truncated or len(texts) < len(found)
        use = AttachmentUse(attachment.name, attachment.mime, kind, len(texts), sum(map(len, texts)), truncated)
        return _Read(use, texts)

    def _sees(self, found: Found, options: LlmOptions) -> bool:
        """Whether the model that answers sees images: the one asked for, or llm's active one."""
        if not found.images or self.vision is None:
            return False
        model = options.model or self.vision.active_model()
        return any(m.vision and m.name == model for m in found.models)

    def _chat(self, id: str | None, laboratory: bool) -> ChatSummary | None:
        if id is None:
            return None
        chat = self.chats.chat(id)
        if chat is None:
            raise NotFound(f"there is no chat {id!r}")
        if chat.laboratory != laboratory:
            kind = "of the laboratory" if chat.laboratory else "official"
            raise Conflict(f"the chat {id!r} is {kind}: ask it {'with' if chat.laboratory else 'without'} `against`")
        return chat

    def ask(self, question: Question) -> Answer:
        config = resolve(self.config)
        laboratory = question.against is not None
        chat = self._chat(question.chat, laboratory)
        history = self.chats.history(chat.id, config.history) if chat is not None and config.history else []
        k = question.k if question.k is not None else config.k

        started = self.clock()
        found = self.search(question.text, k, question.against, question.attachments)
        searched = self.clock()
        cited = [s for s in found.sources if s.score >= config.min_score]
        asked = question.text if question.text.strip() else ATTACHMENT_QUESTION
        model: str | None = None
        text = NOT_FOUND
        if cited:
            images = found.images if self._sees(found, question.llm) else ()
            prompt = with_attachments(asked, found.attachments)
            reply = self.generator.chat(messages(config.prompt, history, cited, prompt, images), question.llm)
            model, text = reply.model, reply.content
        answered = self.clock()

        chat_id, consulta = chat.id if chat is not None else self.new_id(), self.new_id()
        seconds = Seconds(round(searched - started, 3), round(answered - searched, 3) if cited else 0.0)
        stored: QuestionProperties = {
            "pregunta": asked,
            "respuesta": text,
            "modelo_llm": model,
            "modelo_embedding": found.vector.model,
            "k": k,
            "creado_en": self.today(),
            "segundos": round(seconds.search + seconds.answer, 3),
            "laboratorio": laboratory,
            "experimento_embedding": found.experiment,
            "encontrada": bool(cited),
        }
        if found.attachments:  # their names and types, never their content
            stored["adjuntos"] = [use.name for use in found.attachments]
            stored["tipos_adjuntos"] = [use.mime for use in found.attachments]
            stored["caracteres_busqueda"] = sum(use.characters for use in found.attachments)
            stored["trozos_busqueda"] = sum(use.pieces for use in found.attachments)
        self.chats.save(question_batch(chat_id, chat is None, consulta, stored, cited))
        return Answer(text, cited, chat_id, consulta, model, bool(cited), seconds, laboratory, found.attachments)
