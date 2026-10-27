"""ingesta's JSON ↔ chunking models (feature 026). ingesta's keys are memory columns (Spanish); they become
SourceDocument here, and go no further."""

from collections.abc import Mapping

from chunking.adapters.http import Json, QueryParams
from chunking.models import DocumentFilter, SourceDocument, SourceError


def document(row: Json) -> SourceDocument:
    """A FileRecord of ingesta as a SourceDocument."""
    if not isinstance(row, Mapping):
        raise SourceError(f"ingesta answered a file that isn't an object: {row!r}")
    try:
        return SourceDocument(
            origin=str(row["origen"]),
            target=str(row["destino"]),
            name=str(row["nombre"]),
            sha256=str(row["sha256"]) if row.get("sha256") else None,
            file_type=str(row["tipo"]),
            year=int(row["anio"]) if row.get("anio") is not None else None,
            code=str(row["codigo"]) if row.get("codigo") else None,
        )
    except (KeyError, TypeError, ValueError) as e:
        raise SourceError(f"ingesta answered a file without {e}: {row!r}") from e


def filter_params(filter: DocumentFilter) -> QueryParams:
    """The query of GET /data for a filter (`type` repeated, the rest only when set)."""
    params: QueryParams = tuple(("type", t) for t in filter.types)
    optional: list[tuple[str, str | int | None]] = [
        ("year", filter.year),
        ("month", filter.month),
        ("week", filter.week),
        ("code", filter.code),
    ]
    return params + tuple((name, value) for name, value in optional if value is not None)
