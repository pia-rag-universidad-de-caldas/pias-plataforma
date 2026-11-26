"""Asker: a question → its vector (embeddings) → the closest chunks (data) → the answer (llm) → the chat (data).

It always cites: the answer comes with the chunks it was given as context. If no chunk passes min_score, it answers
that it found nothing and never calls the LLM. A module that doesn't answer stops it before anything is stored: the
question, its answer and its citations are one batch, written last.

With attachments (phase 2), each one searches too: a document by its pieces (parsing reads it, nothing is stored), an
image by what a vision model of llm sees in it; every search is joined by best score. The CONSULTA keeps their names
and types, never the files. The attachments are read once (`prepare`): a comparison (feature 060) reuses them in
every panel, each one cutting the pieces to its embeddings model's limit.

Where it searches (`against`): the official chunks with the active model, the official chunks with another model
(`embeddings_model`, feature 060: an official question) or the chunks of an embeddings experiment (the laboratory).
"""

import base64
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from common.clock import now
from consultas.config import (
    ATTACHMENT_QUESTION,
    COURSE_CANDIDATES,
    COURSE_SEARCH,
    DESCRIBE_PROMPT,
    FINISHED_EXPERIMENT,
    MAX_COURSE_DOCUMENTS,
    MAX_SEARCH,
    MAX_TEXTS,
    NOT_FOUND,
)
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
    ConsultasConfig,
    CourseMatch,
    Generator,
    InvalidQuestion,
    LlmModel,
    LlmOptions,
    Message,
    NotFound,
    Prepared,
    PreparedAttachment,
    PreviewedDocument,
    Previewer,
    Question,
    QuestionProperties,
    QuestionVector,
    Response,
    Retriever,
    Role,
    Seconds,
    Source,
    Turn,
    Vectors,
    Vision,
)

from .active_config import resolve
from .attachments import budgets, check, merged, pieces, spread, vision_model
from .courses import named, rerank, topic
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
    courses: list[CourseMatch] = field(default_factory=list)  # the documents the question named: only theirs searched


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
        if against is None or against.embeddings_experiment is None:
            model = against.embeddings_model if against is not None else None
            vector = self.vectors.question(text, model)  # with `model`, its own limit and index (feature 060)
            return vector, vector.index, None
        experiment = self.vectors.experiment(against.embeddings_experiment)
        if experiment is None:
            raise NotFound(f"embeddings has no experiment {against.embeddings_experiment!r}")
        if experiment.status != FINISHED_EXPERIMENT:
            raise Conflict(f"the embeddings experiment {experiment.id!r} is {experiment.status}, not finished")
        vector = self.vectors.question(text, experiment.model, experiment.max_tokens)
        return vector, vector.experiment_index, experiment.id

    def _courses(self, text: str, earlier: Sequence[str]) -> list[CourseMatch]:
        """The documents of the courses the question names (feature 057); if it names none, those the previous
        question of the chat named ("¿y su bibliografía?")."""
        for asked in (text, *earlier[-1:]):
            if asked.strip():
                found = named(asked, self.retriever.courses(asked, COURSE_CANDIDATES))
                if found:
                    return found[:MAX_COURSE_DOCUMENTS]
        return []

    def _official(self, text: str, vector: QuestionVector, k: int, earlier: Sequence[str]) -> Found:
        """Over the chunks of the courses the question names, if it names some (and they have vectors); if not, over
        every official chunk."""
        courses = self._courses(text, earlier)
        if courses:
            sha256s = [c.sha256 for c in courses]
            read = min(k * COURSE_SEARCH, MAX_SEARCH)
            sources = self.retriever.search(vector.index, vector.vector, read, None, sha256s)
            if sources:
                return Found(vector, rerank(sources, topic(text, courses), k), None, courses=courses)
        return Found(vector, self.retriever.search(vector.index, vector.vector, k), None)

    def prepare(self, attachments: Sequence[Attachment]) -> Prepared:
        """The attachments read: each document by parsing, each image described by a vision model of llm. Their
        limits and types are checked first (InvalidQuestion)."""
        if not attachments:
            return Prepared()
        kinds = check(attachments)
        models = tuple(self._models()) if AttachmentKind.IMAGE in kinds else ()
        items = [
            PreparedAttachment(attachment, kind, description=self._describe(attachment, models))
            if kind is AttachmentKind.IMAGE
            else PreparedAttachment(attachment, kind, document=self._preview(attachment))
            for attachment, kind in zip(attachments, kinds, strict=True)
        ]
        return Prepared(tuple(items), models)

    def search(
        self,
        text: str,
        k: int | None = None,
        against: Against | None = None,
        attachments: Sequence[Attachment] = (),
        earlier: Sequence[str] = (),
        prepared: Prepared | None = None,
    ) -> Found:
        """The chunks closest to the question (and to its attachments), best first, without the final LLM and without
        min_score: what was found. An official question that names a course searches only its documents
        (feature 057; `earlier`: the chat's previous questions, oldest first). `prepared`: the attachments already
        read (feature 060); without it, `attachments` are read here."""
        wanted = k if k is not None else resolve(self.config).k
        if not text.strip() and not attachments and (prepared is None or not prepared.items):
            raise InvalidQuestion("a question needs its text or some attachment")
        read_now = prepared if prepared is not None else self.prepare(attachments)
        laboratory = against is not None and against.laboratory
        if not read_now.items:
            vector, index, experiment = self._vector(text, against)
            if not laboratory:
                return self._official(text, vector, wanted, earlier)
            return Found(vector, self.retriever.search(index, vector.vector, wanted, experiment), experiment)
        vector, index, experiment = self._vector(text if text.strip() else ATTACHMENT_QUESTION, against)
        kinds = [item.kind for item in read_now.items]
        read = [
            self._read(item, budget, vector.max_tokens)
            for item, budget in zip(read_now.items, budgets(kinds), strict=True)
        ]
        texts = [piece for r in read for piece in r.texts]
        searches = [self.retriever.search(index, vector.vector, wanted, experiment)] if text.strip() else []
        for start in range(0, len(texts), MAX_TEXTS):
            found = self.vectors.texts(texts[start : start + MAX_TEXTS], vector.model, vector.max_tokens)
            searches += [self.retriever.search(index, v, wanted, experiment) for v in found.vectors]
        sent = tuple(_b64(i.attachment.content) for i in read_now.items if i.kind is AttachmentKind.IMAGE)
        uses = [r.use for r in read]
        return Found(vector, merged(searches, wanted), experiment, uses, sent, list(read_now.models))

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

    def _preview(self, attachment: Attachment) -> PreviewedDocument:
        if self.previewer is None:
            raise InvalidQuestion("documents can't be attached here: consultas has no access to parsing")
        document = self.previewer.preview(attachment.name, attachment.mime, attachment.content)
        if not any(section.text.strip() for section in document.sections):
            raise InvalidQuestion(f"parsing found no text in {attachment.name!r}")
        return document

    def _read(self, item: PreparedAttachment, budget: int, max_tokens: int) -> _Read:
        attachment = item.attachment
        if item.kind is AttachmentKind.IMAGE:
            seen = item.description or ""
            use = AttachmentUse(attachment.name, attachment.mime, item.kind, 1, len(seen), description=seen)
            return _Read(use, [seen])
        document = item.document or PreviewedDocument(attachment.name, 0, False, [])
        found = pieces(document.sections, max_tokens)
        if not found:
            raise InvalidQuestion(f"parsing found no text in {attachment.name!r}")
        texts = spread(found, budget)
        truncated = document.truncated or len(texts) < len(found)
        use = AttachmentUse(attachment.name, attachment.mime, item.kind, len(texts), sum(map(len, texts)), truncated)
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
            raise Conflict(
                f"the chat {id!r} is {kind}: ask it {'with' if chat.laboratory else 'without'}"
                " `against.embeddings_experiment`"
            )
        return chat

    def respond(
        self,
        question: Question,
        history: Sequence[Turn] = (),
        prepared: Prepared | None = None,
        config: ConsultasConfig | None = None,
    ) -> Response:
        """The answer and the CONSULTA to keep, without storing anything (`ask` stores it in its chat; a comparison,
        under its COMPARACION). `history`: the chat's last turns, oldest first."""
        active = config if config is not None else resolve(self.config)
        k = question.k if question.k is not None else active.k
        started = self.clock()
        earlier = [turn.question for turn in history]
        found = self.search(question.text, k, question.against, question.attachments, earlier, prepared)
        searched = self.clock()
        cited = [s for s in found.sources if s.score >= active.min_score]
        asked = question.text if question.text.strip() else ATTACHMENT_QUESTION
        model: str | None = None
        text = NOT_FOUND
        if cited:
            images = found.images if self._sees(found, question.llm) else ()
            prompt = with_attachments(asked, found.attachments)
            reply = self.generator.chat(messages(active.prompt, history, cited, prompt, images), question.llm)
            model, text = reply.model, reply.content
        answered = self.clock()

        seconds = Seconds(round(searched - started, 3), round(answered - searched, 3) if cited else 0.0)
        stored: QuestionProperties = {
            "pregunta": asked,
            "respuesta": text,
            "modelo_llm": model,
            "modelo_embedding": found.vector.model,
            "k": k,
            "creado_en": self.today(),
            "segundos": round(seconds.search + seconds.answer, 3),
            "laboratorio": question.laboratory,
            "experimento_embedding": found.experiment,
            "encontrada": bool(cited),
        }
        if found.attachments:  # their names and types, never their content
            stored["adjuntos"] = [use.name for use in found.attachments]
            stored["tipos_adjuntos"] = [use.mime for use in found.attachments]
            stored["caracteres_busqueda"] = sum(use.characters for use in found.attachments)
            stored["trozos_busqueda"] = sum(use.pieces for use in found.attachments)
        if found.courses:  # the documents of the courses it named: only theirs were searched (feature 057)
            stored["documentos_curso"] = [c.sha256 for c in found.courses]
        return Response(
            text, cited, model, bool(cited), seconds, question.laboratory, found.attachments, found.courses, stored
        )

    def ask(self, question: Question) -> Answer:
        config = resolve(self.config)
        chat = self._chat(question.chat, question.laboratory)
        history = self.chats.history(chat.id, config.history) if chat is not None and config.history else []
        response = self.respond(question, history, config=config)
        chat_id, consulta = chat.id if chat is not None else self.new_id(), self.new_id()
        self.chats.save(question_batch(chat_id, chat is None, consulta, response.stored, response.sources))
        return Answer(
            response.answer,
            response.sources,
            chat_id,
            consulta,
            response.model,
            response.found,
            response.seconds,
            response.laboratory,
            response.attachments,
            response.courses,
        )
