"""Default values of the embeddings module: the only list of embedding models of the project."""

from dataclasses import dataclass
from enum import StrEnum


class Pooling(StrEnum):
    """How a model turns its token vectors into one (what sentence-transformers does for it)."""

    MEAN = "mean"  # the mean of the real tokens (MiniLM, e5)
    CLS = "cls"  # the first token's ([CLS]): bge-m3's dense vector


@dataclass(frozen=True)
class ModelSpec:
    """Both limits count the model's special tokens ([CLS] and [SEP]), as it reads a text. The prefixes are part of
    the text the model reads (e5 was trained with them): they count in its tokens, and chunking's limit (the model's
    minus 2) doesn't know them, so with a passage prefix the pipeline's chunks may go a few tokens over and fail."""

    dimensions: int
    default_tokens: int  # max_seq_length: the limit when nothing else is asked for
    max_tokens: int  # the most that may be asked for: the model's positions (a test checks it with the real model)
    pooling: Pooling = Pooling.MEAN
    query_prefix: str = ""  # in front of a question (POST /vectors)
    passage_prefix: str = ""  # in front of a chunk (runs and experiments)


# The candidates (feature 055) are there to be compared in the laboratory; the active one stays the MiniLM until an
# experiment is applied. A new model is a line here: its vectors get their own property and index by themselves.
MODELS: dict[str, ModelSpec] = {
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": ModelSpec(
        dimensions=384, default_tokens=128, max_tokens=512
    ),
    "intfloat/multilingual-e5-base": ModelSpec(
        dimensions=768, default_tokens=512, max_tokens=512, query_prefix="query: ", passage_prefix="passage: "
    ),
    "BAAI/bge-m3": ModelSpec(dimensions=1024, default_tokens=8192, max_tokens=8192, pooling=Pooling.CLS),
}
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # of the active config when none is set
MODEL_VERSION = 1  # raise it when the way of embedding changes: every document is embedded again
MODEL_CACHE = ".cache/embeddings"  # the one chunking used: nothing is downloaded again. Relative to the project root
EMBEDDING_BATCH = 32  # texts per forward pass of the model
RUN_TIMEOUT = 300.0  # seconds per request to data during a run
MAX_WAITING = 100  # runs and experiments waiting in the line
MAX_TEXTS = 64  # texts per POST /vectors (feature 048)
MAX_TEXT = 20_000  # characters of each one: a question, or a piece of a document (what is longer is cut by tokens)
FINGERPRINT_BATCH = 200  # JSON nodes per batch when a model's fingerprints are removed (feature 055)

# What chunking leaves on a JSON (feature 043): its chunking state. data's schema, not this module's.
CHUNKED_KEY = "estado_chunking"
CHUNKED = "fragmentado"  # its value when the document is chunked
FINISHED_EXPERIMENT = "finished"  # EXPERIMENTO.estado of a chunking experiment that ended well
ACTIVE_CONFIG_ID = "embeddings"  # the CONFIG_OFICIAL node of this module (chunking's is `activa`)
