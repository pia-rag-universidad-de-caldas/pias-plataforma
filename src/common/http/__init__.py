"""What every HTTP client of the modules shares (features 026 and 033): the base client and the page loop."""

from .base_client import CONFLICT, NOT_FOUND, BaseHttpClient, ErrorPolicy, Json, QueryParams, detail, segment
from .pagination import paginate
from .probe import responds

__all__ = [
    "CONFLICT",
    "NOT_FOUND",
    "BaseHttpClient",
    "ErrorPolicy",
    "Json",
    "QueryParams",
    "detail",
    "paginate",
    "responds",
    "segment",
]
