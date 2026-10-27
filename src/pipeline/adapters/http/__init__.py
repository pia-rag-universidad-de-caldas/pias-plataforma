"""What every HTTP client of the pipeline shares: the base client."""

from .base_client import CONFLICT, NOT_FOUND, BaseHttpClient, Json, QueryParams, detail, segment

__all__ = ["CONFLICT", "NOT_FOUND", "BaseHttpClient", "Json", "QueryParams", "detail", "segment"]
