"""data's JSON ↔ chunking models of experiments (features 025 and 026). Property names are stored data (Spanish);
they become chunking models here, and go no further."""

import json
from collections.abc import Mapping

from chunking.adapters.http import Json
from chunking.models import (
    ChunkPiece,
    ConversionProperties,
    ConvertedDocument,
    DocumentFailure,
    DocumentStatus,
    ExperimentChunkProperties,
    ExperimentDocument,
    ExperimentProgress,
    ExperimentProperties,
    ExperimentRecord,
    ExperimentResults,
    ExperimentSection,
    ExperimentSectionProperties,
    ExperimentStatus,
    ExperimentUseProperties,
    GroupResult,
    OfficialDocument,
    OfficialJsonProperties,
    Score,
    ScoreProperties,
    SourceDocument,
    TokenStats,
    rule_index,
)

from .mappers import integer, integers, properties, stored, text, texts


def _loads(value: Json) -> Json:
    try:
        return json.loads(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _number(value: Json) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def _tokens(value: Json) -> TokenStats | None:
    if not isinstance(value, Mapping):
        return None
    return TokenStats(
        integer(value.get("min")) or 0,
        _number(value.get("mean")),
        integer(value.get("p90")) or 0,
        integer(value.get("max")) or 0,
    )


def _groups(value: Json) -> dict[str, GroupResult]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(k): GroupResult(
            integer(g.get("sections")) or 0,
            integer(g.get("chunks")) or 0,
            _tokens(g.get("tokens")),
            _number(g.get("chunking_seconds")),
        )
        for k, g in value.items()
        if isinstance(g, Mapping)
    }


def _results(value: Json) -> ExperimentResults | None:
    data = _loads(value)
    if not isinstance(data, Mapping):
        return None
    return ExperimentResults(
        documents=integer(data.get("documents")) or 0,
        converted=integer(data.get("converted")) or 0,
        reused=integer(data.get("reused")) or 0,
        errors=integer(data.get("errors")) or 0,
        conversion_seconds=_number(data.get("conversion_seconds")),
        chunking_seconds=_number(data.get("chunking_seconds")),
        by_strategy=_groups(data.get("by_strategy")),
        by_rule=_groups(data.get("by_rule")),
        failures=[
            DocumentFailure(str(f.get("error")), text(f.get("origin")), text(f.get("sha256")))
            for f in data.get("failures") or []
            if isinstance(f, Mapping)
        ],
    )


def _progress(value: Json) -> ExperimentProgress:
    data = _loads(value)
    if not isinstance(data, Mapping):
        return ExperimentProgress()
    return ExperimentProgress(**{k: integer(data.get(k)) or 0 for k in ExperimentProgress.__dataclass_fields__})


def record(id: str, raw: Mapping[str, Json]) -> ExperimentRecord:
    """An EXPERIMENTO node."""
    p = stored(raw, ExperimentProperties)
    status = p["estado"]
    return ExperimentRecord(
        id=id,
        name=text(p["nombre"]) or "",
        description=text(p["descripcion"]) or "",
        status=ExperimentStatus(status) if status in {s.value for s in ExperimentStatus} else ExperimentStatus.FAILED,
        created=text(p["creado_en"]) or "",
        finished=text(p["terminado_en"]),
        progress=_progress(p["progreso"]),
        files_json=text(p["archivos"]) or "null",
        conversion_json=text(p["conversion"]) or "null",
        plan_json=text(p["plan"]) or "null",
        results_json=text(p["resultados"]),
        error=text(p["error"]),
        results=_results(p["resultados"]),
    )


def source(raw: Mapping[str, Json]) -> SourceDocument | None:
    """The file an EXP_DOCUMENTO was converted from; None if it has no origen."""
    p = stored(raw, ConversionProperties)
    if text(p["origen"]) is None:
        return None
    return SourceDocument(
        origin=text(p["origen"]) or "",
        target=text(p["destino"]) or "",
        name=text(p["nombre"]) or "",
        sha256=text(p["sha256"]),
        file_type=text(p["tipo"]) or "",
        year=integer(p["anio"]),
        code=text(p["codigo"]),
    )


def document(conversion_id: str, raw: Mapping[str, Json]) -> ExperimentDocument:
    """An EXP_USA relationship (its properties are the summary of the document in the experiment)."""
    p = stored(raw, ExperimentUseProperties)
    return ExperimentDocument(
        sha256=text(p["sha256"]) or conversion_id.split(":")[0],
        conversion_id=conversion_id,
        origin=text(p["origen"]),
        name=text(p["nombre"]),
        code=text(p["codigo"]),
        reused=p["reutilizado"] is True,
        status=DocumentStatus(status) if (status := p["estado"]) in set(DocumentStatus) else DocumentStatus.ERROR,
        error=text(p["error"]),
        sections=integer(p["secciones"]) or 0,
        chunks=integer(p["chunks"]) or 0,
    )


def section(position: int, raw: Mapping[str, Json]) -> ExperimentSection:
    """An EXP_SECCION node; `position` is its index when it has none."""
    p = stored(raw, ExperimentSectionProperties)
    return ExperimentSection(
        index=integer(p["indice"]) or position,
        title=text(p["titulo"]) or "",
        level=integer(p["nivel"]) or 0,
        pages=integers(p["paginas"]),
        rule=rule_index(p["regla"]),
        strategy=text(p["estrategia"]) or "",
        parameters_json=text(p["parametros"]) or "{}",
        chunks=integer(p["chunks"]) or 0,
        tokens=integer(p["tokens"]) or 0,
    )


def piece(raw: Mapping[str, Json]) -> ChunkPiece:
    """An EXP_CHUNK node."""
    p = stored(raw, ExperimentChunkProperties)
    return ChunkPiece(
        text(p["texto"]) or "",
        texts(p["encabezados"]),
        integers(p["paginas"]),
        integer(p["tokens"]) or 0,
    )


def score(raw: Mapping[str, Json]) -> Score | None:
    """An EXP_PUNTUACION node; None if it has no criteria or id."""
    p = stored(raw, ScoreProperties)
    criteria = _loads(p["criterios"])
    if not isinstance(criteria, Mapping) or text(p["puntuacion"]) is None:
        return None
    return Score(
        id=text(p["puntuacion"]) or "",
        criteria={str(k): _number(v) for k, v in criteria.items()},
        created=text(p["creado_en"]) or "",
        modified=text(p["modificado_en"]) or "",
        author=text(p["autor"]),
        comment=text(p["comentario"]),
        target=text(p["objetivo"]),
    )


def conversion(raw: Mapping[str, Json]) -> ConversionProperties:
    """An EXP_DOCUMENTO node, read as its stored shape."""
    return stored(raw, ConversionProperties)


def score_properties(experiment_id: str, score: Score) -> ScoreProperties:
    """The properties of the EXP_PUNTUACION node of a score."""
    return {
        "puntuacion": score.id,
        "experimento": experiment_id,
        "criterios": json.dumps(score.criteria, ensure_ascii=False, sort_keys=True),
        "autor": score.author,
        "comentario": score.comment,
        "objetivo": score.target,
        "creado_en": score.created,
        "modificado_en": score.modified,
    }


def official(node: Json) -> OfficialDocument | None:
    """A JSON node of the official graph (feature 028); None if it isn't a node or has no sha256 (id). One that wasn't
    promoted from a conversion (no readable `contenido`) comes with `content` None."""
    raw = properties(node)
    if raw is None or not isinstance(node, Mapping):
        return None
    p = stored(raw, OfficialJsonProperties)
    sha256 = text(p["sha256"]) or text(node.get("id"))
    if not sha256:
        return None
    content: ConvertedDocument | None = None
    if isinstance(p["contenido"], str):
        try:
            content = ConvertedDocument.from_json(p["contenido"])
        except ValueError:
            content = None
    fingerprint = text(p["fingerprint_conversion"])
    return OfficialDocument(
        document=SourceDocument(
            origin=text(p["origen"]) or "",
            target=text(p["destino"]) or "",
            name=text(p["nombre"]) or "",
            sha256=sha256,
            file_type=text(p["tipo"]) or "",
            year=integer(p["anio"]),
            code=text(p["codigo"]),
        ),
        conversion_id=f"{sha256}:{fingerprint}" if fingerprint else "",
        conversion_json=text(p["conversion"]),
        docling=text(p["docling"]) or "",
        content=content if fingerprint else None,
    )
