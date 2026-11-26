"""Project settings: default paths and organization parameters.

The folder and file NAMES (vacios, vigentes...) are data: they already exist on disk and in the
memory, so they stay in Spanish."""

# Default paths, relative to the project root (resolved by adapters.project_path).
BASE = "data/base"
INGEST = "data/ingesta"
MEMORY_NAME = ".memoria.sqlite3"  # stored inside the ingesta folder

# HTTP API (serve command, feature 016).
API_HOST = "127.0.0.1"  # local only; 0.0.0.0 exposes it on the network
API_PORT = 8000

LEVELS = 5  # anio/mes/semana/codigo/archivo
# Extensions that are the same format and must go to the same folder.
EQUIVALENT_EXTENSIONS = {"jpeg": "jpg", "tif": "tiff", "htm": "html", "yml": "yaml"}
NO_EXTENSION = "sin_extension"
# ingesta/ folders, one per category (see domain.classification); inside, one subfolder per type.
EMPTY_FOLDER = "vacios"  # 0 B or almost empty (overrides everything else)
UNSUPPORTED_FOLDER = "archivos_extranios"  # types that are not in SUPPORTED_TYPES
HASH_DUPLICATES_FOLDER = "hash_duplicados"  # same sha256 as a newer one
CODE_DUPLICATES_FOLDER = "codigos_duplicados"  # same code as a newer one
CURRENT_FOLDER = "vigentes"  # the rest: what gets chunked
INCOMPLETE_FOLDER = "formato_incompleto"  # they don't follow anio/mes/semana/codigo/archivo
# Almost empty: from 1 B to less than this threshold. The corpus has a clear cut at 1 KB:
# below it, mostly ~160 B .txt files; from 2 KB on, thousands of small but real PDFs.
ALMOST_EMPTY_THRESHOLD = 1024  # bytes
# Types (normalized extension) that get chunked; the rest goes to UNSUPPORTED_FOLDER.
SUPPORTED_TYPES = frozenset({"pdf", "doc", "docx"})
# Code of the courses without an assigned code: it groups different PIAA, so it doesn't count as repeated.
UNASSIGNED_CODE = "000000"
NO_PIAA_MARK = "SIN_PIAA"  # in the name of the template uploaded when there is no PIAA
PARTIAL_SUFFIX = ".parcial"  # temporary name while a file is copied

# Uploads through the API (feature 049): data/base/<anio>/<mes>/<semana>/<codigo>/<archivo>, as the corpus names them.
MONTH_FOLDERS = (
    "01_Enero", "02_Febrero", "03_Marzo", "04_Abril", "05_Mayo", "06_Junio",
    "07_Julio", "08_Agosto", "09_Septiembre", "10_Octubre", "11_Noviembre", "12_Diciembre",
)  # fmt: skip
WEEK_DAYS = 7  # Semana_01 = days 1-7 of the month, Semana_02 = 8-14... (Semana_05: 29-31)
CODE_DIGITS = 6  # the code folder: six digits (UNASSIGNED_CODE included)
MAX_NAME = 200  # bytes (UTF-8) of an uploaded name: with its prefix and a __N it still fits in 255

PROGRESS_EVERY = 500  # every how many copied files the progress is reported
HASH_BATCH = 1000  # hashes computed per save in the memory

# The chunkable files in data (feature 042): each one a RAW node, published at the end of every ingestion.
RAW_LIMIT = 32 * 1024 * 1024  # largest body data accepts (the server's max_body_bytes); a bigger file isn't published
RAW_TIMEOUT = 120.0  # seconds per request to data while publishing (a file of a few MB in base64)
RAW_PAGE = 200  # RAW nodes per page when reading which ones data has (without their content)
RAW_RETIRE_BATCH = 200  # RAW marked as no longer current per batch

# Statistics (GET /stats)
MAX_TYPES = 7  # the rest is grouped into "otros" (max. 8 distinguishable colors)
TOP_DUPLICATES = 25  # duplicate groups listed by /stats
TOP_EMPTY = 50  # empty or almost empty files listed by /stats
TOP_REPEATED = 50  # code-years with the most files listed by /stats
