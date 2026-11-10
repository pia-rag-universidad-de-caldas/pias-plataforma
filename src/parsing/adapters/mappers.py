"""What is read from data, into models: the only place where the stored (Spanish) names become concepts. A TypedDict
doesn't check anything at run time, so every value is checked here."""

import base64
import binascii
from collections.abc import Mapping
from typing import cast

from common.http import Json
from parsing.domain import decode
from parsing.models import PageCoverage, ParseStatus, RawFile, RawProperties, RawState, StoredParse

_STATUSES = {s.value: s for s in ParseStatus}


def _text(value: Json) -> str | None:
    return value if isinstance(value, str) and value else None


def _integer(value: Json) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _pages(value: Json) -> list[int]:
    return [v for v in value if isinstance(v, int)] if isinstance(value, list) else []


def raw_state(sha256: str, raw: Mapping[str, Json]) -> RawState:
    p = cast(RawProperties, raw)
    vigente = p.get("vigente", True)
    status = _STATUSES.get(_text(p.get("estado_parseo")) or "")
    return RawState(sha256, vigente is not False, status, _text(p.get("fingerprint_parseo")))


def raw_file(sha256: str, raw: Mapping[str, Json]) -> RawFile | None:
    """None if its content can't be read (no `contenido`, not base64)."""
    p = cast(RawProperties, raw)
    content = p.get("contenido")
    if not isinstance(content, str):
        return None
    try:
        decoded = base64.b64decode(content, validate=True)
    except (binascii.Error, ValueError):
        return None
    name = _text(p.get("nombre")) or f"{sha256}.{_text(p.get('tipo')) or 'pdf'}"
    return RawFile(sha256, name, _text(p.get("tipo")) or "", _text(p.get("codigo")), decoded)


def stored_parse(raw: Mapping[str, Json]) -> StoredParse | None:
    """What a JSON node has of an earlier parsing of this module; None if it isn't one (an older JSON)."""
    status = _STATUSES.get(_text(raw.get("estado")) or "")
    fingerprint, text = _text(raw.get("fingerprint_parseo")), _text(raw.get("documento"))
    document = decode(text) if text else None
    if status is None or fingerprint is None or document is None:
        return None
    coverage = PageCoverage(
        total=_integer(raw.get("paginas_totales")),
        processed=_integer(raw.get("paginas_procesadas")),
        pending=_pages(raw.get("paginas_pendientes")),
        without_text=_pages(raw.get("paginas_sin_texto")),
        reason=_text(raw.get("error")),
    )
    return StoredParse(document, coverage, status, fingerprint)
