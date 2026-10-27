"""Pipeline parameters and the location of the other modules in the single server."""

# Prefix of each module in the server (server.app mounts them there).
INGESTA_PATH = "/ingesta"
DATA_PATH = "/data"
CHUNKING_PATH = "/chunking"

TEMPLATE = "piaa"  # the default template (POST /pipeline/runs without `template`); it can't be deleted
ACTORS = ("lab", "lab2", "embeber", "modelscenter")  # known actors at start, without callback_url

SELECT_PER_PAGE = 50  # files per page when a selection doesn't say `per_page` (the same default as /ingesta/data)
MAX_SELECT_PER_PAGE = 500  # the largest page of /ingesta/data and /data/nodes
GRAPH_PAGE_SIZE = 500  # nodes per page when the store reads every run or template

HTTP_TIMEOUT = 5.0  # seconds: health and actor notifications
RUN_TIMEOUT = 60.0  # seconds per request while a stage runs
POLL_INTERVAL = 2.0  # seconds between two reads of a running chunking experiment
BUSY_RETRY = 5.0  # seconds to wait when chunking answers 409 (another experiment or run is running)
EXPERIMENT_TIMEOUT = 24 * 3600.0  # seconds a chunking experiment may take (waiting for its turn included)
