"""Pipeline parameters and the location of the other modules in the single server."""

from common.config import MAX_PER_PAGE, PER_PAGE

TEMPLATE = "produccion"  # the default template (POST /pipeline/runs without `template`); it can't be deleted
LAB_TEMPLATE = "laboratorio"
EXPERIMENTS_TEMPLATE = "experimentos"  # feature 062: choose parsed documents, chunk them in an experiment, embed
ACTORS = ("lab",)  # known actors at start, without callback_url (feature 044: the laboratory's only actor)
SCOPES = ("new", "all")  # what a production run chunks and embeds: the freshly parsed, or every parsed document

SELECT_PER_PAGE = PER_PAGE  # files per page when a selection doesn't say `per_page`
MAX_SELECT_PER_PAGE = MAX_PER_PAGE  # the largest page of /ingesta/data and /data/nodes
SEED_LIMIT = 2**31  # the seed drawn for a sample asked without one (062): data draws an unseeded sample on every page
GRAPH_PAGE_SIZE = MAX_PER_PAGE  # nodes per page when the store reads every run or template

# Where an actor's notice may go (feature 040): this machine, plus the hosts of the variable (comma separated).
CALLBACK_HOSTS = ("localhost", "127.0.0.1", "::1")
CALLBACK_HOSTS_VARIABLE = "PIPELINE_CALLBACK_HOSTS"

RUN_TIMEOUT = 60.0  # seconds per request while a stage runs
POLL_INTERVAL = 2.0  # seconds between two reads of something running in another module
BUSY_RETRY = 5.0  # seconds to wait when a module answers 409 (its line is full, or another run is going)
EXPERIMENT_TIMEOUT = 24 * 3600.0  # seconds a job of another module may take (waiting for its turn included)

# The embedding model's token limit counts its two special tokens ([CLS] and [SEP]); chunking's tokenizer doesn't
# count them: a chunk may have at most (limit - SPECIAL_TOKENS) tokens, and embeddings gets max_tokens + SPECIAL_TOKENS.
SPECIAL_TOKENS = 2

# The routes of the other modules (features 042, 043 and 046), under each module's prefix.
INGESTA_RUNS = "/runs"  # POST (202, 409 if another runs), GET /runs/{id}
INGESTA_RUNNING = frozenset({"en_curso"})  # IngestionState while it runs; "terminada" ends well, "fallida" not
INGESTA_DONE = frozenset({"terminada"})
PARSING_RUNS = "/runs"  # POST {sha256s, redo, simulate} (202), GET /runs/{id}
CHUNKING_EXPERIMENTS = "/experiments"  # POST, GET /experiments/{id}, POST /experiments/{id}/apply
CHUNKING_RUNS = "/runs"  # POST {sha256s} (202), GET /runs/{id}: the official chunking (feature 045)
EMBEDDINGS_RUNS = "/runs"  # POST {sha256s} (202, the active configuration), GET /runs/{id}
EMBEDDINGS_EXPERIMENTS = "/experiments"  # POST {name, description, chunking_experiment, model, max_tokens}, .../apply
EMBEDDINGS_MODELS = "/models"  # GET: [{name, default_tokens, max_tokens, default}]
LLM_MODELS = "/models"  # GET: {admitted: [{name, context, vision, installed, default}], installed: [...]} (feature 047)
LLM_CONFIG = "/config"  # PUT {model, temperature?, num_ctx?, max_tokens?, system?}: the active configuration
ALIVE = frozenset({"queued", "running"})  # the status of a job of parsing, chunking or embeddings that isn't over
SUCCEEDED = frozenset({"finished", "done"})  # one that ended well
# The graph label of an embeddings experiment (feature 046), for PIPE_USA: the iteration links it as it links the
# chunking ones (it is also in the iteration's `experimentos_embeddings`). None would leave it unlinked.
EMBEDDINGS_EXPERIMENT_LABEL: str | None = "EXP_EMBEDDINGS"

# Feature 062: the experiments pipeline.
DATA_SELECT = (
    "/documents/select"  # POST {universe, files, exclude_experiment?, page, per_page} → {total, sha256s, pages}
)
DATA_EXPERIMENT = "/nodes/EXPERIMENTO"  # GET /{id}?omit=...: the chunking experiment's `estado`, as data has it
EXPERIMENT_OMIT = ("documentos", "resultados", "progreso")  # what the wait doesn't need of an EXPERIMENTO
PARSED_UNIVERSE = "parsed"  # the parsed JSON (parseado/parcial): what a chunking experiment can take
CHUNKED_UNIVERSE = "chunked"  # the officially chunked JSON (fragmentado): what `official` embeds
CHUNKING_CONFIG = "/config"  # GET: the active configuration (`chunking`: its resolved parameters)
CHUNKING_GOES_ON = frozenset({"finished", "partial"})  # an experiment that ended: embeddings takes what it chunked
CHUNKING_RESUMABLE = frozenset({"partial", "failed", "interrupted"})  # POST /chunking/experiments/{id}/resume takes it
