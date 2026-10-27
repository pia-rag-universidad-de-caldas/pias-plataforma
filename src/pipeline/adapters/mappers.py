"""The pipeline's models as graph properties and back: the only place where the stored (Spanish) names meet the
models. What is nested goes as JSON text (Neo4j stores no maps); reading checks it and a malformed node is an
UnavailableError (data holds something the pipeline didn't write)."""

import json
from collections.abc import Mapping

from pipeline.models import (
    Event,
    EventProperties,
    Iteration,
    IterationProperties,
    JsonObject,
    JsonValue,
    PipelineError,
    PipelineRun,
    RunProperties,
    RunStatus,
    Template,
    TemplateProperties,
    UnavailableError,
    as_object,
    cursor_from_json,
    cursor_to_json,
    event_from_json,
    event_to_json,
    iteration_from_json,
    iteration_to_json,
    record_from_json,
    record_to_json,
    selection_from_json,
    selection_to_json,
    stages_from_json,
    stages_to_json,
    waiting_from_json,
    waiting_to_json,
)

from .http import Json


def dumps(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(text: object, where: str) -> JsonValue:
    if not isinstance(text, str):
        raise UnavailableError(f"{where} isn't JSON text: {text!r}")
    try:
        value: JsonValue = json.loads(text)
    except ValueError as e:
        raise UnavailableError(f"{where} isn't valid JSON: {e}") from e
    return value


def _list(value: JsonValue, where: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise UnavailableError(f"{where} isn't a list")
    return value


def _text(raw: Mapping[str, Json], key: str) -> str:
    value = raw.get(key)
    return value if isinstance(value, str) else ""


def _optional(raw: Mapping[str, Json], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) and value else None


# --- templates ---


def template_properties(template: Template) -> TemplateProperties:
    return {
        "nombre": template.name,
        "descripcion": template.description,
        "etapas": dumps(stages_to_json(template.stages)),
        "predefinida": template.builtin,
        "creado_en": template.created,
        "modificado_en": template.modified,
    }


def template_from(id: str, raw: Mapping[str, Json]) -> Template:
    try:
        stages = stages_from_json(loads(raw.get("etapas"), f"PIPELINE {id}.etapas"))
    except PipelineError as e:
        raise UnavailableError(f"the stored template {id} is malformed: {e}") from e
    return Template(
        id=id,
        name=_text(raw, "nombre"),
        description=_text(raw, "descripcion"),
        stages=stages,
        builtin=raw.get("predefinida") is True,
        created=_text(raw, "creado_en"),
        modified=_text(raw, "modificado_en"),
    )


def template_to_json(template: Template) -> JsonObject:
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "builtin": template.builtin,
        "stages": stages_to_json(template.stages),
        "created": template.created,
        "modified": template.modified,
    }


def template_from_json(value: JsonValue) -> Template:
    raw = as_object(value, "template")
    return Template(
        id=str(raw.get("id") or ""),
        name=str(raw.get("name") or ""),
        description=str(raw.get("description") or ""),
        stages=stages_from_json(raw.get("stages")),
        builtin=raw.get("builtin") is True,
        created=str(raw.get("created") or ""),
        modified=str(raw.get("modified") or ""),
    )


# --- runs ---


def _stage_at(run: PipelineRun) -> str | None:
    top = run.template.stages
    if run.cursor.stage >= len(top):
        return None
    stage = top[run.cursor.stage]
    return stage.stages[run.cursor.step].id if run.cursor.step is not None else stage.id


def run_properties(run: PipelineRun) -> RunProperties:
    properties: RunProperties = {
        "nombre": run.name,
        "plantilla": run.template.id,
        "plantilla_copia": dumps(template_to_json(run.template)),
        "estado": run.status.value,
        "parametros": dumps(dict(run.params.items())),
        "cursor": dumps(cursor_to_json(run.cursor)),
        "artefactos": dumps(run.artifacts),
        "iteraciones": dumps([iteration_to_json(i) for i in run.iterations]),
        "registros": dumps([record_to_json(r) for r in run.records]),
        "eventos": dumps([event_to_json(e) for e in run.events]),
        "creado_en": run.created,
    }
    if run.files is not None:
        properties["archivos"] = dumps(selection_to_json(run.files))
    if run.waiting is not None:
        properties["espera"] = dumps(waiting_to_json(run.waiting))
        properties["actor"] = run.waiting.actor
    if run.started:
        properties["iniciado_en"] = run.started
    if run.finished:
        properties["terminado_en"] = run.finished
    if run.error:
        properties["error"] = run.error
    stage = _stage_at(run)
    if stage:
        properties["etapa"] = stage
    return properties


def run_from(id: str, raw: Mapping[str, Json]) -> PipelineRun:
    where = f"PIPE_CORRIDA {id}"
    try:
        params = as_object(loads(raw.get("parametros"), f"{where}.parametros"), f"{where}.parametros")
        files = raw.get("archivos")
        waiting = raw.get("espera")
        return PipelineRun(
            id=id,
            name=_text(raw, "nombre"),
            template=template_from_json(loads(raw.get("plantilla_copia"), f"{where}.plantilla_copia")),
            status=RunStatus(_text(raw, "estado")),
            created=_text(raw, "creado_en"),
            files=None if files is None else selection_from_json(loads(files, f"{where}.archivos")),
            params={k: as_object(v, f"{where}.parametros.{k}") for k, v in params.items()},
            cursor=cursor_from_json(loads(raw.get("cursor"), f"{where}.cursor")),
            artifacts=as_object(loads(raw.get("artefactos"), f"{where}.artefactos"), f"{where}.artefactos"),
            iterations=tuple(
                iteration_from_json(i) for i in _list(loads(raw.get("iteraciones"), where), f"{where}.iteraciones")
            ),
            records=tuple(record_from_json(r) for r in _list(loads(raw.get("registros"), where), f"{where}.registros")),
            events=tuple(event_from_json(e) for e in _list(loads(raw.get("eventos"), where), f"{where}.eventos")),
            waiting=None if waiting is None else waiting_from_json(loads(waiting, f"{where}.espera")),
            started=_optional(raw, "iniciado_en"),
            finished=_optional(raw, "terminado_en"),
            error=_optional(raw, "error"),
        )
    except (PipelineError, ValueError) as e:
        if isinstance(e, UnavailableError):
            raise
        raise UnavailableError(f"the stored run {id} is malformed: {e}") from e


def iteration_id(run: PipelineRun, iteration: Iteration) -> str:
    return f"{run.id}:{iteration.stage}:{iteration.index}"


def iteration_properties(run: PipelineRun, iteration: Iteration) -> IterationProperties:
    properties: IterationProperties = {
        "corrida": run.id,
        "etapa": iteration.stage,
        "indice": iteration.index,
        "estado": iteration.status.value,
        "configuracion": dumps(iteration.config),
        "artefactos": dumps(iteration.artifacts),
        "experimentos": list(iteration.experiments),
        "iniciado_en": iteration.started,
    }
    if iteration.score is not None:
        properties["puntuacion"] = dumps(iteration.score)
    if iteration.finished:
        properties["terminado_en"] = iteration.finished
    return properties


def event_id(run: PipelineRun, event: Event) -> str:
    return f"{run.id}:e{event.index}"


def event_properties(run: PipelineRun, event: Event) -> EventProperties:
    return {
        "corrida": run.id,
        "indice": event.index,
        "actor": event.actor,
        "tipo": event.kind,
        "detalle": dumps(event.detail),
        "creado_en": event.created,
    }
