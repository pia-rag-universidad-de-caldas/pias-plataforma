"""Technical values the modules share (feature 040): what makes them fit together. No business rule lives here."""

# Prefix of each module in the single server (server.app mounts them there).
INGESTA_PATH = "/ingesta"
DATA_PATH = "/data"
CHUNKING_PATH = "/chunking"
PIPELINE_PATH = "/pipeline"
PARSING_PATH = "/parsing"  # feature 042
EMBEDDINGS_PATH = "/embeddings"  # feature 046
LLM_PATH = "/llm"  # feature 047
CONSULTAS_PATH = "/consultas"  # feature 048

PER_PAGE = 50  # items per page of a listing if no other size is requested
MAX_PER_PAGE = 500  # the largest page any listing gives
HTTP_TIMEOUT = 5.0  # seconds of a quick request to another module (health checks)
