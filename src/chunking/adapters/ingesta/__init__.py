"""ingesta over HTTP (feature 026): its client and the mapping of its JSON to chunking models."""

from .files_client import IngestaFilesClient
from .mappers import document, filter_params

__all__ = ["IngestaFilesClient", "document", "filter_params"]
