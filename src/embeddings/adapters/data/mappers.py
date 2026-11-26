"""data's nodes and rows as embeddings' values: the only place where the names stored in Spanish become models. A
value of an unexpected type is read as missing: the document then fails or waits, never the run."""

from collections.abc import Mapping

from common.http import Json
from embeddings.config import CHUNKED, CHUNKED_KEY
from embeddings.models import (
    ConfigOrigin,
    EmbeddableChunk,
    EmbeddableDocument,
    EmbeddingConfig,
)


def text(raw: Mapping[str, Json], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) else None


def integer(raw: Mapping[str, Json], key: str) -> int | None:
    value = raw.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


FINGERPRINT = "huella_embedding_"  # huella_embedding_<model>_<dim> (feature 055): one per model


def fingerprints(raw: Mapping[str, Json]) -> dict[str, str]:
    """The fingerprint of each model a JSON was embedded with, by its key."""
    return {key: value for key, value in raw.items() if key.startswith(FINGERPRINT) and isinstance(value, str)}


EMBEDDED_OVER = "huella_chunking_embedding_"  # huella_chunking_embedding_<model>_<dim> (feature 057)


def document(sha256: str, raw: Mapping[str, Json], file_name: str | None = None) -> EmbeddableDocument:
    """An official JSON: whether chunking left it chunked, what each model's vectors came from and over which
    chunks; `file_name`, its RAW's."""
    over = {key: value for key, value in raw.items() if key.startswith(EMBEDDED_OVER) and isinstance(value, str)}
    return EmbeddableDocument(
        sha256, raw.get(CHUNKED_KEY) == CHUNKED, fingerprints(raw), text(raw, "huella_chunking"), over, file_name
    )


def chunk(id: str, raw: Mapping[str, Json]) -> EmbeddableChunk:
    """A FRAGMENTOS or an EXP_CHUNK: the text with its headings (texto_contextualizado), or the bare one if it has
    none."""
    return EmbeddableChunk(id, text(raw, "texto_contextualizado") or text(raw, "texto") or "")


def config(raw: Mapping[str, Json]) -> EmbeddingConfig | None:
    """This module's CONFIG_OFICIAL; None if it can't be read (then the default applies)."""
    model, limit, origin = text(raw, "modelo"), integer(raw, "max_tokens"), text(raw, "origen")
    if model is None or limit is None:
        return None
    known = {o.value for o in ConfigOrigin}
    return EmbeddingConfig(
        model,
        limit,
        ConfigOrigin(origin) if origin in known else ConfigOrigin.MANUAL,
        text(raw, "experimento"),
        text(raw, "modificado_en"),
    )
