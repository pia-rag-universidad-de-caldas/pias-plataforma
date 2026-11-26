"""Chunking settings that aren't Docling's (feature 043: those are in docling.py). The base URL of data comes from
ServerSettings.self_url."""

from common.config import MAX_PER_PAGE

TOKENIZER_CACHE = ".cache/tokenizers"  # relative to the project root: downloaded once, then read offline

# The other modules, as prefixes of the same server (feature 020): chunking only talks to data (feature 043).
SELF_URL = "http://127.0.0.1:8000"  # used only when the app is built without a server (python -m server sets it)
RUN_TIMEOUT = 120.0  # seconds per request during an experiment or a run (reading a large document)

GRAPH_PAGE_SIZE = MAX_PER_PAGE  # nodes asked to GET /data/nodes/{label} at a time
