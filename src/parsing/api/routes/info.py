"""GET /config (the fixed configuration) and GET /health (Docling, the OCR engine and data)."""

from fastapi import APIRouter

from common.http import responds
from parsing.adapters import DoclingParser
from parsing.api.app_info import VERSION
from parsing.api.dependencies import DocumentParser, Settings
from parsing.api.schemas import ConfigView, HealthStatus
from parsing.config import PARSING, PARSING_VERSION
from parsing.domain import fingerprint

router = APIRouter(tags=["info"])


@router.get("/config")
def read_config(parser: DocumentParser) -> ConfigView:
    """What every parsing uses: nothing of it can be asked in a request. Changing it is changing
    parsing/config/docling.py and raising its version: everything is then pending to be parsed again."""
    docling = parser.version()
    found = fingerprint(PARSING, PARSING_VERSION, docling) if docling else None
    return ConfigView(PARSING_VERSION, docling, found, PARSING.as_dict())


@router.get("/health")
def health(settings: Settings, parser: DocumentParser) -> HealthStatus:
    # Synchronous route: it runs in a thread, so the server is free to answer the request it makes to itself.
    installed, ocr = parser.available(), parser.ocr_available()
    data = responds(settings.self_url, f"{settings.data_path}/health")
    no_doc = isinstance(parser, DoclingParser) and "doc" in parser.unavailable_types()
    return HealthStatus(
        status="ok" if installed and ocr and data else "degraded",
        version=VERSION,
        docling="installed" if installed else "missing",
        docling_version=parser.version(),
        ocr="installed" if ocr else "missing",
        libreoffice="missing" if no_doc else "installed",
        data="ok" if data else "unavailable",
    )
