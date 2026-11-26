"""The answers of embeddings, llm, data and parsing as consultas' values: the only place where the names stored in
Spanish become models. An answer of another shape is the module's fault: its *Down error (503), never a made-up
value."""

import json
from collections.abc import Mapping

from common.http import Json
from consultas.models import (
    Against,
    AttachmentKind,
    AttachmentUse,
    ChatSummary,
    ChunkingExperiment,
    CitedChunk,
    ComparisonSummary,
    ConfigOrigin,
    ConsultasConfig,
    CourseMatch,
    Coverage,
    EmbeddingModel,
    EmbeddingsExperiment,
    EmbeddingsRun,
    LlmModel,
    LlmOptions,
    ModuleDown,
    PanelAnswer,
    PanelResult,
    PanelStatus,
    PreviewedDocument,
    PreviewSection,
    QuestionVector,
    Reply,
    Seconds,
    Source,
    StoredQuestion,
    TextVectors,
)


def text(raw: Mapping[str, Json], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) else None


def integer(raw: Mapping[str, Json], key: str) -> int | None:
    value = raw.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def number(raw: Mapping[str, Json], key: str) -> float | None:
    value = raw.get(key)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def texts(raw: Mapping[str, Json], key: str) -> list[str]:
    value = raw.get(key)
    return [str(v) for v in value] if isinstance(value, list) else []


def integers(raw: Mapping[str, Json], key: str) -> list[int]:
    value = raw.get(key)
    return [v for v in value if isinstance(v, int) and not isinstance(v, bool)] if isinstance(value, list) else []


def _object(raw: Json, what: str, error: type[ModuleDown]) -> Mapping[str, Json]:
    if not isinstance(raw, Mapping):
        raise error(f"it answered {what} that isn't an object: {str(raw)[:300]}")
    return raw


# embeddings


def text_vectors(raw: Json, count: int, error: type[ModuleDown]) -> TextVectors:
    """POST /embeddings/vectors with `count` texts: one vector each, of the model's dimensions."""
    body = _object(raw, "the vectors", error)
    model, index, experiment_index = text(body, "model"), text(body, "index"), text(body, "experiment_index")
    max_tokens, dimensions, vectors = integer(body, "max_tokens"), integer(body, "dimensions"), body.get("vectors")
    if model is None or index is None or experiment_index is None or max_tokens is None or dimensions is None:
        raise error(f"it answered vectors without their model or indexes: {str(raw)[:300]}")
    if not isinstance(vectors, list) or len(vectors) != count or not all(isinstance(v, list) for v in vectors):
        raise error(f"it didn't answer one vector for each of the {count} texts")
    found = [[float(v) for v in row if isinstance(v, (int, float)) and not isinstance(v, bool)] for row in vectors]
    for vector in found:
        if len(vector) != dimensions:
            raise error(f"it answered a vector of {len(vector)} values for a model of {dimensions} dimensions")
    return TextVectors(model, max_tokens, dimensions, index, experiment_index, found)


def question_vector(raw: Json, error: type[ModuleDown]) -> QuestionVector:
    """POST /embeddings/vectors with one text."""
    found = text_vectors(raw, 1, error)
    return QuestionVector(
        found.model, found.max_tokens, found.dimensions, found.index, found.experiment_index, found.vectors[0]
    )


def experiment(raw: Json, error: type[ModuleDown]) -> EmbeddingsExperiment:
    """GET /embeddings/experiments/{id}: its status and its configuration."""
    body = _object(raw, "an experiment", error)
    config = _object(body.get("config"), "the configuration of an experiment", error)
    id, status, model, limit = (
        text(body, "id"),
        text(body, "status"),
        text(config, "model"),
        integer(config, "max_tokens"),
    )
    if id is None or status is None or model is None or limit is None:
        raise error(f"it answered an experiment without its id, status or model: {str(raw)[:300]}")
    return EmbeddingsExperiment(id, status, model, limit)


# llm


def reply(raw: Json, error: type[ModuleDown]) -> Reply:
    """POST /llm/chat."""
    body = _object(raw, "the chat", error)
    message = _object(body.get("message"), "the message of the chat", error)
    model, content = text(body, "model"), text(message, "content")
    if model is None or content is None:
        raise error(f"it answered without the model or the content: {str(raw)[:300]}")
    return Reply(
        model, content, integer(body, "prompt_tokens"), integer(body, "answer_tokens"), number(body, "seconds")
    )


def models(raw: Json, error: type[ModuleDown]) -> list[LlmModel]:
    """GET /llm/models: the admitted ones."""
    body = _object(raw, "the models", error)
    admitted = body.get("admitted")
    if not isinstance(admitted, list):
        raise error(f"it answered the models without the admitted ones: {str(raw)[:300]}")
    found: list[LlmModel] = []
    for row in admitted:
        model = _object(row, "a model", error)
        name = text(model, "name")
        if name is not None:
            found.append(LlmModel(name, model.get("vision") is True, model.get("installed") is True))
    return found


def active_model(raw: Json, error: type[ModuleDown]) -> str:
    """GET /llm/config: its model."""
    model = text(_object(raw, "the configuration", error), "model")
    if model is None:
        raise error(f"it answered a configuration without its model: {str(raw)[:300]}")
    return model


# parsing


def previewed(raw: Json, error: type[ModuleDown]) -> PreviewedDocument:
    """POST /parsing/preview."""
    body = _object(raw, "the preview", error)
    sections = body.get("sections")
    if not isinstance(sections, list):
        raise error(f"it answered a preview without its sections: {str(raw)[:300]}")
    found = []
    for row in sections:
        section = _object(row, "a section", error)
        found.append(PreviewSection(texts(section, "headings"), text(section, "text") or ""))
    return PreviewedDocument(
        text(body, "name") or "", integer(body, "pages") or 0, body.get("truncated") is True, found
    )


# data


def properties(node: Json) -> Mapping[str, Json] | None:
    """The properties of a node as data answers it ({label, id, properties}); None if it isn't one."""
    if not isinstance(node, Mapping):
        return None
    found = node.get("properties")
    return found if isinstance(found, Mapping) else {}


def source(raw: Json, error: type[ModuleDown]) -> Source:
    """A row of POST /data/vectors/search."""
    body = _object(raw, "a search row", error)
    score = number(body, "score")
    id, sha256 = text(body, "id"), text(body, "sha256")
    if id is None or score is None or sha256 is None:
        raise error(f"it answered a search row without its id, score or sha256: {str(raw)[:300]}")
    return Source(
        id=id,
        score=score,
        text=text(body, "text") or "",
        headings=texts(body, "headings"),
        pages=integers(body, "pages"),
        sha256=sha256,
        origin=text(body, "origin"),
        code=text(body, "code"),
        activity=text(body, "activity"),
    )


def course(raw: Json, error: type[ModuleDown]) -> CourseMatch:
    """A row of POST /data/documents/search (feature 057)."""
    body = _object(raw, "a document search row", error)
    sha256 = text(body, "sha256")
    if sha256 is None:
        raise error(f"it answered a document search row without its sha256: {str(raw)[:300]}")
    return CourseMatch(
        sha256, text(body, "name"), text(body, "activity_code"), number(body, "score") or 0.0, text(body, "origin")
    )


def chat(id: str, raw: Mapping[str, Json]) -> ChatSummary:
    created = text(raw, "creado_en") or ""
    return ChatSummary(
        id, text(raw, "titulo") or "", created, text(raw, "modificado_en") or created, raw.get("laboratorio") is True
    )


def stored_question(id: str, raw: Mapping[str, Json], sources: list[CitedChunk]) -> StoredQuestion:
    return StoredQuestion(
        id=id,
        question=text(raw, "pregunta") or "",
        answer=text(raw, "respuesta") or "",
        llm_model=text(raw, "modelo_llm"),
        embedding_model=text(raw, "modelo_embedding") or "",
        k=integer(raw, "k") or 0,
        created=text(raw, "creado_en") or "",
        seconds=number(raw, "segundos") or 0.0,
        laboratory=raw.get("laboratorio") is True,
        embeddings_experiment=text(raw, "experimento_embedding"),
        sources=sources,
        attachments=texts(raw, "adjuntos"),
    )


def cited(id: str, label: str, link: Mapping[str, Json], chunk: Mapping[str, Json] | None) -> CitedChunk:
    """A RESPONDIDA_CON with the chunk it goes to (None if it is no longer there)."""
    found = chunk or {}
    return CitedChunk(
        id=id,
        label=label,
        score=number(link, "puntaje") or 0.0,
        order=integer(link, "orden") or 0,
        text=text(found, "texto") or "",
        headings=texts(found, "encabezados"),
        pages=integers(found, "paginas"),
    )


def config(raw: Mapping[str, Json]) -> ConsultasConfig | None:
    """This module's CONFIG_OFICIAL; None if it can't be read (then the default applies)."""
    k, min_score, prompt, history = (
        integer(raw, "k"),
        number(raw, "min_score"),
        text(raw, "prompt"),
        integer(raw, "historia"),
    )
    if k is None or min_score is None or prompt is None or history is None:
        return None
    origin = text(raw, "origen")
    known = {o.value for o in ConfigOrigin}
    return ConsultasConfig(
        k,
        min_score,
        prompt,
        history,
        ConfigOrigin(origin) if origin in known else ConfigOrigin.MANUAL,
        text(raw, "modificado_en"),
    )


# Feature 060: what can be asked, and the comparisons.


def embedding_models(raw: Json, error: type[ModuleDown]) -> list[EmbeddingModel]:
    """GET /embeddings/models."""
    if not isinstance(raw, list):
        raise error(f"it answered the models with something that isn't a list: {str(raw)[:300]}")
    found: list[EmbeddingModel] = []
    for row in raw:
        model = _object(row, "a model", error)
        name, dimensions, vector_property = (
            text(model, "name"),
            integer(model, "dimensions"),
            text(model, "vector_property"),
        )
        if name is None or dimensions is None or not vector_property:
            raise error(f"it answered a model without its name, dimensions or vector_property: {str(row)[:300]}")
        found.append(EmbeddingModel(name, dimensions, vector_property))
    return found


def embeddings_model(raw: Json, error: type[ModuleDown]) -> str:
    """GET /embeddings/config: its model."""
    model = text(_object(raw, "the configuration", error), "model")
    if model is None:
        raise error(f"it answered a configuration without its model: {str(raw)[:300]}")
    return model


def embeddings_runs(raw: Json, error: type[ModuleDown]) -> list[EmbeddingsRun]:
    """GET /embeddings/experiments: the model at the top (feature 059) or in its `config`; the documents with vectors,
    `embedded`."""
    if not isinstance(raw, list):
        raise error(f"it answered the experiments with something that isn't a list: {str(raw)[:300]}")
    found: list[EmbeddingsRun] = []
    for row in raw:
        body = _object(row, "an experiment", error)
        config = body.get("config")
        model = text(body, "model") or (text(config, "model") if isinstance(config, Mapping) else None)
        id, status = text(body, "id"), text(body, "status")
        if id is None or status is None or model is None:
            raise error(f"it answered an experiment without its id, status or model: {str(row)[:300]}")
        embedded = body.get("embedded")
        found.append(
            EmbeddingsRun(
                id,
                text(body, "name") or "",
                status,
                model,
                integer(body, "dimensions"),
                text(body, "chunking_experiment"),
                len(embedded) if isinstance(embedded, list) else 0,
            )
        )
    return found


def coverage(raw: Json, error: type[ModuleDown]) -> Coverage:
    """GET /data/progress/embeddings."""
    body = _object(raw, "the progress", error)
    done, total = integer(body, "done"), integer(body, "total")
    if done is None or total is None:
        raise error(f"it answered a progress without done or total: {str(raw)[:300]}")
    return Coverage(done, total)


def chunking_experiment(id: str, node: Mapping[str, Json]) -> ChunkingExperiment:
    """The EXPERIMENTO node chunking left in data: `nombre` and `chunking`, its ChunkingParameters as JSON text
    (English keys: chunker, tokenizer, max_tokens...). consultas reads it from data, never from chunking: modules
    don't call each other. A `chunking` that isn't readable JSON leaves the parameters empty."""
    raw = node.get("chunking")
    parameters: Json = None
    if isinstance(raw, str):
        try:
            parameters = json.loads(raw)
        except ValueError:
            parameters = None
    chunking: Mapping[str, Json] = parameters if isinstance(parameters, Mapping) else {}
    return ChunkingExperiment(
        id,
        text(node, "nombre") or "",
        text(chunking, "chunker"),
        text(chunking, "tokenizer"),
        integer(chunking, "max_tokens"),
    )


def _against(raw: Json) -> Against | None:
    if not isinstance(raw, Mapping):
        return None
    experiment, model = text(raw, "experimento_embedding"), text(raw, "modelo_embedding")
    if experiment is None and model is None:
        return None
    return Against(experiment, None if experiment is not None else model)


def _llm(raw: Json) -> LlmOptions:
    if not isinstance(raw, Mapping):
        return LlmOptions()
    return LlmOptions(
        text(raw, "modelo"), number(raw, "temperatura"), integer(raw, "num_ctx"), integer(raw, "max_tokens")
    )


def stored_panels(raw: Mapping[str, Json]) -> list[tuple[PanelResult, str | None, str | None]]:
    """The `paneles` JSON of a COMPARACION: each panel without its answer, its CONSULTA and the LLM that answered.
    What can't be read is left out (a panel is never made up)."""
    try:
        panels = json.loads(text(raw, "paneles") or "[]")
    except json.JSONDecodeError:
        return []
    found: list[tuple[PanelResult, str | None, str | None]] = []
    for position, panel in enumerate(panels if isinstance(panels, list) else []):
        if not isinstance(panel, Mapping):
            continue
        status = PanelStatus.OK if text(panel, "estado") == PanelStatus.OK.value else PanelStatus.ERROR
        index = integer(panel, "indice")
        result = PanelResult(
            index if index is not None else position,
            text(panel, "etiqueta") or f"Panel {position + 1}",
            _against(panel.get("destino")),
            _llm(panel.get("llm")),
            integer(panel, "k"),
            status,
            text(panel, "error"),
        )
        found.append((result, text(panel, "consulta"), text(panel, "modelo_llm")))
    return found


def comparison_summary(id: str, raw: Mapping[str, Json]) -> ComparisonSummary:
    panels = stored_panels(raw)
    models: list[str] = []
    for result, _, answered in panels:
        model = answered or result.llm.model
        if model is not None and model not in models:
            models.append(model)
    return ComparisonSummary(id, text(raw, "pregunta") or "", text(raw, "creado_en") or "", len(panels), models)


def cited_source(id: str, link: Mapping[str, Json], chunk: Mapping[str, Json] | None) -> tuple[int, Source]:
    """A RESPONDIDA_CON of a comparison's CONSULTA, with the chunk it goes to (None if it is no longer there), and its
    order."""
    found = chunk or {}
    source = Source(
        id=id,
        score=number(link, "puntaje") or 0.0,
        text=text(found, "texto") or "",
        headings=texts(found, "encabezados"),
        pages=integers(found, "paginas"),
        sha256=text(link, "sha256") or "",
        origin=text(link, "origen"),
        code=text(link, "codigo"),
        activity=text(link, "actividad"),
    )
    return integer(link, "orden") or 0, source


def _json_rows(raw: Mapping[str, Json], key: str) -> list[Mapping[str, Json]]:
    try:
        rows = json.loads(text(raw, key) or "[]")
    except json.JSONDecodeError:
        return []
    return [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def _use(row: Mapping[str, Json]) -> AttachmentUse:
    known = {k.value for k in AttachmentKind}
    kind = text(row, "tipo")
    return AttachmentUse(
        text(row, "nombre") or "",
        text(row, "mime") or "",
        AttachmentKind(kind) if kind in known else AttachmentKind.DOCUMENT,
        integer(row, "trozos") or 0,
        integer(row, "caracteres") or 0,
        row.get("truncado") is True,
        text(row, "descripcion"),
    )


def _course(row: Mapping[str, Json]) -> CourseMatch:
    return CourseMatch(
        text(row, "sha256") or "",
        text(row, "nombre"),
        text(row, "codigo_actividad"),
        number(row, "puntaje") or 0.0,
        text(row, "origen"),
    )


def panel_answer(consulta: str, raw: Mapping[str, Json], sources: list[Source]) -> PanelAnswer:
    """A comparison's CONSULTA as the panel answered it."""
    return PanelAnswer(
        answer=text(raw, "respuesta") or "",
        sources=sources,
        consulta=consulta,
        model=text(raw, "modelo_llm"),
        found=raw.get("encontrada") is True,
        seconds=Seconds(number(raw, "segundos_busqueda") or 0.0, number(raw, "segundos_respuesta") or 0.0),
        laboratory=raw.get("laboratorio") is True,
        attachments=[_use(row) for row in _json_rows(raw, "uso_adjuntos")],
        courses=[_course(row) for row in _json_rows(raw, "cursos")],
    )
