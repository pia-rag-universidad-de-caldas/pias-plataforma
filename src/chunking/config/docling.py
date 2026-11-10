"""Everything about Docling's chunking in one place (feature 043): what can be asked for, its default, and what is
fixed.

Only four things are configurable, in an experiment and in the active configuration: the chunker, the tokenizer,
max_tokens and merge_peers (these two only with `hybrid`). Everything else is CHUNKING_FIXED: changing a value of it is
raising CHUNKING_VERSION, which enters every fingerprint, so what was chunked before is pending again.
"""

from dataclasses import dataclass

# The chunkers of docling-core that can be asked for (DoclingChunker values).
CHUNKERS = ("hybrid", "hierarchical", "page")

# The tokenizers a request may ask for: each one is downloaded once to TOKENIZER_CACHE, so only names listed here (never
# any text from a request) reach the Hugging Face Hub. Add one here to allow it.
TOKENIZERS = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",  # multilingual (the corpus is in Spanish)
    "sentence-transformers/all-MiniLM-L6-v2",  # HybridChunker's own default (English)
)
MAX_TOKENS_RANGE = (16, 8192)  # what a request may ask for


@dataclass(frozen=True)
class ChunkingDefault:
    """What is used when nobody set the active configuration (or for what a request leaves out)."""

    chunker: str = "hybrid"
    tokenizer: str = TOKENIZERS[0]
    # The default embedding model (paraphrase-multilingual-MiniLM-L12-v2) has max_seq_length 128, and those 128 count
    # its two special tokens ([CLS] and [SEP]), which docling-core's HuggingFaceTokenizer doesn't count: a chunk must be
    # 2 tokens shorter than the model limit, or the embedding cuts it.
    max_tokens: int = 126
    merge_peers: bool = True


CHUNKING_DEFAULT = ChunkingDefault()


@dataclass(frozen=True)
class ChunkingFixed:
    """What no request can change. The reason of each value is in spec/features/043-chunking-con-docling/spec.md."""

    table_format: str = "triplets"  # docling-core's chunking serializer: "row, column = value" per cell
    repeat_table_header: bool = False  # with triplets each cell already carries its headers
    layers: tuple[str, ...] = ("body",)  # page headers and footers are out: repeated noise on every page
    pictures: str = "caption"  # only their caption: there is no picture description
    formatting: bool = False  # **bold** and _italic_ marks only spend tokens
    hyperlinks: bool = True  # the PIAA bibliographies use them
    merge_list_items: bool = True  # hierarchical: a list is one idea
    expand: bool = False  # TreeChunkExpander could go over max_tokens
    always_emit_headings: bool = False  # it would give chunks with only a title
    contextualize: bool = True  # the headings in front: what gets embedded, and what tokens count


CHUNKING_FIXED = ChunkingFixed()
CHUNKING_VERSION = 1  # raise it when CHUNKING_FIXED (or how it is applied) changes: everything is chunked again
