"""What every HTTP client of chunking shares (feature 026): the base client and the page loop."""

from .base_client import NOT_FOUND, BaseHttpClient, ErrorPolicy, Json, QueryParams, detail, segment
from .pagination import paginate

__all__ = ["NOT_FOUND", "BaseHttpClient", "ErrorPolicy", "Json", "QueryParams", "detail", "paginate", "segment"]
