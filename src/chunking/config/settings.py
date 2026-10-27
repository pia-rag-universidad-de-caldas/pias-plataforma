"""Chunking defaults (features 021-023). The base URL of the other modules comes from ServerSettings.self_url."""

# Chunking parameters (features 023 and 025): the defaults of a run; POST /chunking/runs can ask for others
# ("parameters"). All of them enter ChunkingParameters.fingerprint, so changing any reprocesses.
STRATEGY = "hybrid"  # hybrid, element, section, page, fixed, points or semantic (ChunkingStrategy)
MAX_TOKENS = 512  # no chunk goes over this size, counted with TOKENIZER
MAX_TOKENS_RANGE = (16, 8192)  # what a run may ask for
TOKENIZER = "sentence-transformers/all-MiniLM-L6-v2"  # Hugging Face tokenizer (HybridChunker's default)
# The tokenizers a run may ask for: each one is downloaded once to TOKENIZER_CACHE, so only names listed here (never
# any text from a request) reach the Hugging Face Hub. Add one here to allow it.
TOKENIZERS = (
    TOKENIZER,
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",  # multilingual (the corpus is in Spanish)
)
MERGE_PEERS = True  # HybridChunker merges small consecutive chunks with the same headings
# HybridChunker repeats a table's header rows in each piece of a split table. Off by default: with it, docling-core
# counts only the table text against max_tokens and the headings put in front can push a chunk over the limit (then
# the document ends as an error, never stored with an oversized chunk).
REPEAT_TABLE_HEADER = False
TABLE_STRUCTURE = True  # Docling's table structure model (TableFormer) on PDFs
TABLE_MODE = "accurate"  # TableFormer: "accurate" or "fast"
OVERLAP_TOKENS = 64  # strategy "fixed": tokens shared by consecutive windows (always < max_tokens)
# Strategy "semantic": the local embedding models a run may ask for (downloaded once to EMBEDDING_CACHE, then read
# offline; never a remote service). Add one here to allow it.
EMBEDDING_MODELS = ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",)
EMBEDDING_MODEL = EMBEDDING_MODELS[0]
SIMILARITY_THRESHOLD = 0.5  # strategy "semantic": consecutive units are joined while their similarity stays >= this
EMBEDDING_CACHE = ".cache/embeddings"  # relative to the project root
EMBEDDING_BATCH = 32  # texts embedded at a time
TOKENIZER_CACHE = ".cache/tokenizers"  # relative to the project root: downloaded once, then read offline
DOCUMENT_TIMEOUT = 600.0  # seconds Docling may spend on one PDF before giving up (the document ends as an error)

# The graph (feature 023): the PIAA code that isn't one (ingesta's UNASSIGNED_CODE) is never linked.
UNASSIGNED_CODE = "000000"

# The other modules, as prefixes of the same server (feature 020).
SELF_URL = "http://127.0.0.1:8000"  # used only when the app is built without a server (python -m server sets it)
INGESTA_PATH = "/ingesta"
DATA_PATH = "/data"
HTTP_TIMEOUT = 5.0  # seconds per request to another module (health checks)
RUN_TIMEOUT = 120.0  # seconds per request during a run (downloading a large file, writing a large batch)

# Paging (feature 022).
CHUNK_PAGE_SIZE = 20  # files asked to GET /ingesta/data at a time during a run
GRAPH_PAGE_SIZE = 500  # nodes asked to GET /data/nodes/JSON at a time (data's MAX_PER_PAGE)
PER_PAGE = 50  # documents per page of GET /chunking/documents if no other size is requested
MAX_PER_PAGE = 500
SELECTION_MAX_PER_PAGE = (
    500  # `per_page` of an experiment's page range (feature 028): ingesta's and data's MAX_PER_PAGE
)

# Scores of experiments (feature 025, test structure): free criteria; these are the test ones, always summarized.
SCORE_CRITERIA = ("coherencia", "completitud", "tamano")
SCORE_MIN = 0.0
SCORE_MAX = 5.0
HEADING_LEVEL = 1  # conversion of experiments: titles of this level or above start a section
NUMBERED_TITLES = True  # conversion of experiments: Roman-numbered list items ("I.", "III.1.") are titles
