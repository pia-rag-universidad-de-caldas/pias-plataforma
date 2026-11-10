"""HttpRawStore (feature 042): the RAW nodes of data, over HTTP (data is the storage of every module).

    GET  {data}/nodes/RAW?omit=contenido&page&per_page   which ones data has, without their content
    POST {data}/batch                                     one RAW per batch (merge: parsing's properties stay)

The node's properties are stored in Neo4j: their names stay in Spanish.
"""

import base64
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager

import httpx

from common.http import BaseHttpClient, ErrorPolicy, Json, paginate
from ingesta.config import RAW_PAGE, RAW_RETIRE_BATCH, RAW_TIMEOUT
from ingesta.models import FileRecord, RawFileRejected, RawStoreError

RAW = "RAW"
MERGE = "merge"  # data's NodeMode: the properties sent are set, the others (parsing's) kept
_ERRORS = ErrorPolicy("data", RawStoreError, RawFileRejected)


def raw_properties(record: FileRecord, content: bytes, at: str) -> dict[str, object]:
    """What ingesta writes on a RAW: the file and where it comes from."""
    return {
        "origen": record.origen,
        "destino": record.destino,
        "nombre": record.nombre,
        "tipo": record.tipo,
        "mime": record.mime,
        "anio": record.anio,
        "mes": record.mes,
        "semana": record.semana,
        "codigo": record.codigo,
        "tamano": record.bytes,
        "modificado": record.modificado,
        "subido_en": at,
        "vigente": True,
        "contenido": base64.b64encode(content).decode("ascii"),
    }


def _node(sha256: str, properties: Mapping[str, object]) -> dict[str, object]:
    return {"label": RAW, "id": sha256, "properties": dict(properties), "mode": MERGE}


class HttpRawStore(BaseHttpClient):
    """`path`: data's prefix in the server (/data)."""

    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, path, _ERRORS)

    def _page(self, page: int) -> Json:
        return self._get(f"/nodes/{RAW}", (("omit", "contenido"), ("page", page), ("per_page", RAW_PAGE)))

    def published(self) -> Mapping[str, bool]:
        found: dict[str, bool] = {}
        for body in paginate(self._page, "pages", RawStoreError):
            for node in body.get("nodes") or []:
                if isinstance(node, Mapping) and "id" in node:
                    properties = node.get("properties") or {}
                    found[str(node["id"])] = bool(properties.get("vigente", True))
        return found

    def _batch(self, nodes: list[dict[str, object]]) -> None:
        if self._request("POST", "/batch", body={"nodes": nodes, "relationships": []}) is None:
            raise RawStoreError(f"data has no {self._path}/batch route")

    def publish(self, record: FileRecord, content: bytes, at: str) -> None:
        self._batch([_node(record.sha256 or "", raw_properties(record, content, at))])

    def retire(self, sha256s: Sequence[str]) -> None:
        for start in range(0, len(sha256s), RAW_RETIRE_BATCH):
            self._batch([_node(sha256, {"vigente": False}) for sha256 in sha256s[start : start + RAW_RETIRE_BATCH]])


@contextmanager
def raw_store(base_url: str, path: str) -> Iterator[HttpRawStore]:
    """A store on its own HTTP client, closed at the end."""
    with httpx.Client(base_url=base_url, timeout=RAW_TIMEOUT) as client:
        yield HttpRawStore(client, path)
