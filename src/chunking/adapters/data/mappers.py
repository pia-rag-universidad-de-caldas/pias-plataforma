"""data's JSON ↔ chunking models (features 026 and 043). The graph's property names are stored data (Spanish); they
become chunking models here, and go no further."""

import json
from collections.abc import Iterable, Mapping
from typing import cast

from chunking.adapters.http import Json
from chunking.models import (
    ActiveConfig,
    ChunkingParameters,
    ChunkingRun,
    ConfigOrigin,
    ConfigProperties,
    DoclingChunker,
    DocumentFailure,
    DocumentResult,
    DocumentUse,
    ExperimentProgress,
    ExperimentProperties,
    ExperimentRecord,
    ExperimentResults,
    ExperimentStatus,
    ExperimentUseProperties,
    GraphBatch,
    JsonChunkingProperties,
    NodeKey,
    ParsedDocument,
    ParsedJsonProperties,
    RequestedChunking,
    RunProgress,
    RunProperties,
    RunStatus,
    TokenStats,
)

# Readers of one stored value: the type, or nothing (a property written by someone else is ignored, not trusted).


def text(value: Json) -> str | None:
    return None if value is None else str(value)


def integer(value: Json) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def number(value: Json) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def texts(value: Json) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def boolean(value: Json) -> bool | None:
    return value if isinstance(value, bool) else None


def loads(value: Json) -> Json:
    """A property stored as JSON text, read back; None if it isn't."""
    try:
        loaded: Json = json.loads(value) if isinstance(value, str) else None
    except ValueError:
        return None
    return loaded


def properties(node: Json) -> Mapping[str, Json] | None:
    """The properties of a node as data answers it, or None if it isn't one."""
    if not isinstance(node, Mapping) or not isinstance(node.get("properties"), Mapping):
        return None
    found: Mapping[str, Json] = node["properties"]
    return found


class _Lenient(dict[str, Json]):
    """What data answered, read as a stored shape: a key it lacks reads as None, as .get would."""

    def __missing__(self, key: str) -> None:
        return None


def stored[T](raw: Mapping[str, Json], shape: type[T]) -> T:
    """`raw` read as the TypedDict `shape` of models/stored.py: read it by indexing (p["key"]), so that mypy checks
    every key; the values are not checked here (each reader above does)."""
    return cast(T, _Lenient(raw))


# Bodies sent to data


def key_body(key: NodeKey) -> dict[str, str]:
    return {"label": key.label.value, "id": key.id}


def batch_body(batch: GraphBatch) -> dict[str, object]:
    """The body of POST /data/batch."""
    return {
        "replace_from": key_body(batch.replace_from) if batch.replace_from else None,
        "nodes": [{**key_body(n.key), "properties": n.properties, "mode": n.mode.value} for n in batch.nodes],
        "relationships": [
            {
                "type": r.type.value,
                "source": key_body(r.source),
                "target": key_body(r.target),
                "properties": r.properties,
            }
            for r in batch.links
        ],
    }


# Read back


def parsed(sha256: str, raw: Mapping[str, Json]) -> ParsedDocument:
    """A JSON node: what parsing left on it (the document as stored) and what chunking added."""
    p = stored(raw, ParsedJsonProperties)
    c = stored(raw, JsonChunkingProperties)
    return ParsedDocument(
        sha256=text(p["sha256"]) or sha256,
        status=text(p["estado"]) or "",
        parse_fingerprint=text(p["fingerprint_parseo"]) or "",
        content=text(p["documento"]),
        chunked=text(c["huella_chunking"]) if c["estado_chunking"] == "fragmentado" else None,
        chunks=integer(c["fragmentos"]) or 0,
        configuration=text(c["config_chunking"]),
    )


def official_parameters(raw: Mapping[str, Json]) -> ChunkingParameters | None:
    """The parameters the official chunks of a JSON were made with; None if it has none."""
    c = stored(raw, JsonChunkingProperties)
    chunker, tokenizer, version = c["chunker"], text(c["tokenizador"]), integer(c["version_chunking"])
    if c["estado_chunking"] != "fragmentado" or chunker not in {k.value for k in DoclingChunker}:
        return None
    if tokenizer is None or version is None:
        return None
    return ChunkingParameters(
        DoclingChunker(chunker),
        tokenizer,
        integer(c["max_tokens"]),
        boolean(c["fusionar_vecinos"]),
        version,
        text(c["docling_core"]) or "",
    )


def chunking_parameters(value: Json) -> ChunkingParameters | None:
    """ChunkingParameters as stored (asdict, as JSON text); None if it can't be read."""
    data = loads(value)
    if not isinstance(data, Mapping) or data.get("chunker") not in {c.value for c in DoclingChunker}:
        return None
    tokenizer, version = text(data.get("tokenizer")), integer(data.get("chunking_version"))
    if tokenizer is None or version is None:
        return None
    return ChunkingParameters(
        chunker=DoclingChunker(str(data["chunker"])),
        tokenizer=tokenizer,
        max_tokens=integer(data.get("max_tokens")),
        merge_peers=boolean(data.get("merge_peers")),
        chunking_version=version,
        docling_version=text(data.get("docling_version")) or "",
    )


def _failures(found: Json) -> list[DocumentFailure]:
    """The failures, already loaded."""
    if not isinstance(found, list):
        return []
    return [
        DocumentFailure(str(f.get("sha256") or ""), str(f.get("error") or "")) for f in found if isinstance(f, Mapping)
    ]


def _tokens(value: Json) -> TokenStats | None:
    if not isinstance(value, Mapping):
        return None
    low, mean, p90, high = (
        integer(value.get("min")),
        number(value.get("mean")),
        integer(value.get("p90")),
        integer(value.get("max")),
    )
    if low is None or mean is None or p90 is None or high is None:
        return None
    return TokenStats(low, mean, p90, high)


def results(value: Json) -> ExperimentResults | None:
    """ExperimentResults as stored; None if it can't be read."""
    data = loads(value)
    if not isinstance(data, Mapping):
        return None
    counts = {k: integer(data.get(k)) for k in ("documents", "chunked", "errors", "unparsed", "chunks")}
    if any(v is None for v in counts.values()):
        return None
    by_document = [
        DocumentResult(str(d.get("sha256") or ""), integer(d.get("chunks")) or 0, integer(d.get("tokens")) or 0)
        for d in (data.get("by_document") or [])
        if isinstance(d, Mapping)
    ]
    return ExperimentResults(
        documents=counts["documents"] or 0,
        chunked=counts["chunked"] or 0,
        errors=counts["errors"] or 0,
        unparsed=counts["unparsed"] or 0,
        chunks=counts["chunks"] or 0,
        tokens=_tokens(data.get("tokens")),
        seconds=number(data.get("seconds")) or 0.0,
        by_document=by_document,
        failures=_failures(data.get("failures")),
    )


def _counts(value: Json, names: Iterable[str]) -> dict[str, int]:
    """Counters stored as JSON text: each one that isn't an integer reads as 0."""
    data = loads(value)
    return {k: (integer(data.get(k)) if isinstance(data, Mapping) else None) or 0 for k in names}


def record(id: str, raw: Mapping[str, Json]) -> ExperimentRecord:
    p = stored(raw, ExperimentProperties)
    status = p["estado"]
    return ExperimentRecord(
        id=id,
        name=text(p["nombre"]) or "",
        description=text(p["descripcion"]) or "",
        status=ExperimentStatus(status) if status in {s.value for s in ExperimentStatus} else ExperimentStatus.FAILED,
        created=text(p["creado_en"]) or "",
        finished=text(p["terminado_en"]),
        progress=ExperimentProgress(**_counts(p["progreso"], ExperimentProgress.__dataclass_fields__)),
        documents_json=text(p["documentos"]) or "null",
        chunking_json=text(p["chunking"]) or "null",
        results_json=text(p["resultados"]),
        error=text(p["error"]),
        results=results(p["resultados"]),
        started=text(p["iniciado_en"]),
        parameters=chunking_parameters(p["chunking"]),
    )


def config(raw: Mapping[str, Json]) -> ActiveConfig | None:
    """A CONFIG_OFICIAL; None if it can't be read (then the default applies)."""
    p = stored(raw, ConfigProperties)
    chunker, origin = p["chunker"], p["origen"]
    if chunker not in {c.value for c in DoclingChunker} or origin not in {o.value for o in ConfigOrigin}:
        return None
    requested = RequestedChunking(
        DoclingChunker(chunker), text(p["tokenizador"]), integer(p["max_tokens"]), boolean(p["fusionar_vecinos"])
    )
    return ActiveConfig(requested, ConfigOrigin(origin), text(p["experimento"]), text(p["modificado_en"]))


def run(id: str, raw: Mapping[str, Json]) -> ChunkingRun | None:
    """A CORRIDA_CHUNKING; None if it can't be read (one of before feature 045). One still queued or running that this
    server doesn't have was interrupted (whoever reads it answers those it has from its registry)."""
    p = stored(raw, RunProperties)
    parameters, requested, documents = (
        chunking_parameters(p["parametros"]),
        text(p["pedido_en"]),
        loads(p["documentos"]),
    )
    if parameters is None or requested is None or not isinstance(documents, list):
        return None
    status = p["estado"]
    ended = status in {s.value for s in RunStatus} and status not in (RunStatus.QUEUED.value, RunStatus.RUNNING.value)
    return ChunkingRun(
        id=id,
        status=RunStatus(status) if ended else RunStatus.INTERRUPTED,
        requested=requested,
        simulate=boolean(p["simulacion"]) or False,
        parameters=parameters,
        sha256s=texts(documents),
        frozen=p["congelada"] is not False,
        page=integer(p["pagina"]),
        per_page=integer(p["por_pagina"]),
        experiment=text(p["experimento_config"]),
        started=text(p["inicio"]),
        finished=text(p["fin"]),
        progress=RunProgress(**_counts(p["progreso"], RunProgress.__dataclass_fields__)),
        failures=_failures(loads(p["fallos"])),
        chunked=texts(loads(p["fragmentados"])),
        error=text(p["error"]),
        resumed=integer(p["retomada"]) or 0,
    )


def use(sha256: str, raw: Mapping[str, Json]) -> DocumentUse:
    """An EXP_USA: what an experiment did with one document."""
    p = stored(raw, ExperimentUseProperties)
    tokens = p["tokens_por_chunk"]
    return DocumentUse(
        sha256=text(p["sha256"]) or sha256,
        chunked=p["estado"] == "fragmentado",
        chunks=integer(p["chunks"]) or 0,
        tokens=[t for t in tokens if isinstance(t, int)] if isinstance(tokens, list) else [],
    )
