"""data's JSON ↔ chunking models of production (feature 026). The graph's property names are stored data (Spanish);
they become chunking models here, and go no further. The readers (`text`, `integer`...) are shared with
experiment_mappers.py."""

from collections.abc import Mapping
from typing import cast

from chunking.adapters.http import Json
from chunking.models import (
    Chunk,
    ChunkingParameters,
    ChunkProperties,
    DocumentStatus,
    GraphBatch,
    JsonProperties,
    NodeKey,
    ParametersProperties,
    ProcessedDocument,
    Section,
    SectionProperties,
    TableMode,
)

# Readers of one stored value: the type, or nothing (a property written by someone else is ignored, not trusted).


def text(value: Json) -> str | None:
    return None if value is None else str(value)


def integer(value: Json) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def texts(value: Json) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def integers(value: Json) -> list[int]:
    return [v for v in value if isinstance(v, int)] if isinstance(value, list) else []


def boolean(value: Json) -> bool | None:
    return value if isinstance(value, bool) else None


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


# Nodes of production read back


def parameters(raw: Mapping[str, Json]) -> ChunkingParameters | None:
    """The chunking parameters stored on a JSON node (Hierarchy.parameters); None if any is missing."""
    p = stored(raw, ParametersProperties)
    tokenizer, max_tokens, docling = text(p["tokenizador"]), integer(p["max_tokens"]), text(p["docling"])
    flags = [boolean(p["fusionar_vecinos"]), boolean(p["repetir_encabezado_tabla"]), boolean(p["estructura_tablas"])]
    mode = p["modo_tablas"]
    if tokenizer is None or max_tokens is None or docling is None or mode not in {m.value for m in TableMode}:
        return None
    merge_peers, repeat_table_header, table_structure = flags
    if merge_peers is None or repeat_table_header is None or table_structure is None:
        return None
    return ChunkingParameters(
        tokenizer, max_tokens, merge_peers, repeat_table_header, table_structure, TableMode(mode), docling
    )


def processed(node: Json) -> ProcessedDocument | None:
    """A JSON node as a ProcessedDocument; None if it wasn't written by a production run (no origen, or an estado
    that isn't `fragmentado`/`error`: an official JSON only converted, feature 028, isn't one)."""
    raw = properties(node)
    if raw is None:
        return None
    p = stored(raw, JsonProperties)
    origin, status = text(p["origen"]), p["estado"]
    if origin is None or status not in {DocumentStatus.CHUNKED.value, DocumentStatus.ERROR.value}:
        return None
    return ProcessedDocument(
        origin=origin,
        sha256=text(p["sha256"]) or str(node.get("id")),
        fingerprint=text(p["fingerprint"]) or "",
        status=DocumentStatus(status),
        target=text(p["destino"]),
        file_type=text(p["tipo"]),
        year=integer(p["anio"]),
        code=text(p["codigo"]),
        error=text(p["error"]),
        chunked_at=text(p["fragmentado_en"]),
        chunks=integer(p["fragmentos"]) or 0,
        parameters=parameters(raw),
    )


def section(raw: Mapping[str, Json]) -> Section:
    p = stored(raw, SectionProperties)
    return Section(integer(p["orden"]) or 0, texts(p["encabezados"]))


def chunk(node: Json) -> Chunk:
    p = stored(properties(node) or {}, ChunkProperties)
    return Chunk(
        index=integer(p["indice"]) or 0,
        text=text(p["texto"]) or "",
        contextualized_text=text(p["texto_contextualizado"]) or "",
        headings=texts(p["encabezados"]),
        pages=integers(p["paginas"]),
        tokens=integer(p["tokens"]) or 0,
    )
