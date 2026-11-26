"""DoclingChunkers (Chunker, feature 043): docling-core's chunkers over a DoclingDocument that parsing stored (feature
042), always loaded inside the methods (deferred, with import_module): without the `chunk` extra the rest of the server
keeps working and type-checks. docling-core is untyped from here on (Any is admitted in adapters/).

    stored `documento` → base64 → gzip → JSON → DoclingDocument.model_validate
        → HybridChunker | HierarchicalChunker | PageChunker (with CHUNKING_FIXED) → chunks → contextualize

One chunker per parameters and one tokenizer per name are built once and reused. The tokenizers are downloaded once to
TOKENIZER_CACHE and then read offline.
"""

import base64
import binascii
import gzip
import threading
from collections.abc import Callable
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from chunking.config import CHUNKING_FIXED, TOKENIZER_CACHE
from chunking.models import (
    Chunk,
    Chunker,
    ChunkerUnavailable,
    ChunkingError,
    ChunkingParameters,
    DoclingChunker,
    fitted_count,
)

type Docling = Any  # an object of docling-core or transformers (untyped from here)
type TokenizerFactory = Callable[[str, int], Docling]  # (name, max_tokens) → a docling-core BaseTokenizer

MISSING = "docling-core is not installed: uv sync --extra chunk"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_UNLIMITED = 1_000_000  # the limit given to a tokenizer that only counts (hierarchical, page)


def pretrained(kind: Docling, name: str, cache: str) -> Docling:
    """From `cache` without network; downloaded there the first time."""
    try:
        return kind.from_pretrained(name, cache_dir=cache, local_files_only=True)
    except OSError:
        return kind.from_pretrained(name, cache_dir=cache)


def decode(stored: str) -> Docling:
    """The DoclingDocument of a stored `documento` (base64 of gzip of its JSON); ChunkingError if it isn't one."""
    try:
        text = gzip.decompress(base64.b64decode(stored, validate=True)).decode("utf-8")
    except (binascii.Error, OSError, EOFError, UnicodeDecodeError, ValueError) as error:
        raise ChunkingError(f"the stored document can't be read: {type(error).__name__}: {error}") from error
    document_class = import_module("docling_core.types.doc").DoclingDocument
    try:
        return document_class.model_validate_json(text)
    except ValueError as error:  # pydantic's ValidationError is a ValueError
        raise ChunkingError(f"the stored document isn't a DoclingDocument: {error}") from error


def encode(document_json: str) -> str:
    """The stored form of a DoclingDocument's JSON (what parsing writes): for tests and tools."""
    return base64.b64encode(gzip.compress(document_json.encode("utf-8"))).decode("ascii")


class DoclingChunkers(Chunker):
    def __init__(self, tokenizers: TokenizerFactory | None = None, cache: str | None = None) -> None:
        self._cache = cache or str(_PROJECT_ROOT / TOKENIZER_CACHE)
        self._factory = tokenizers or self._huggingface
        self._lock = threading.Lock()
        self._loaded: dict[str, Docling] = {}  # transformers tokenizers by name
        self._chunkers: dict[str, Docling] = {}  # by parameters fingerprint

    def available(self) -> bool:
        return find_spec("docling_core") is not None

    def version(self) -> str | None:
        try:
            return version("docling-core")
        except PackageNotFoundError:
            return None

    def chunk(self, content: str, parameters: ChunkingParameters) -> list[Chunk]:
        chunker = self._ready(parameters)  # first: what the machine lacks stops everything, before any document
        document = decode(content)
        try:
            found = [self._chunk(i, c, chunker) for i, c in enumerate(chunker.chunk(dl_doc=document))]
        except Exception as error:  # anything docling-core raises over this document
            raise ChunkingError(f"{type(error).__name__}: {error}".strip()) from error
        limit = parameters.max_tokens
        oversized = [c.index for c in found if limit is not None and c.tokens > limit]
        if oversized:  # the promise is that no chunk goes over max_tokens: never store one that does
            raise ChunkingError(f"chunks {oversized} have more than {limit} tokens")
        for budget in parameters.fit:  # and, with fit, over any tokenizer's budget (feature 062)
            over = [c.index for c in found if c.tokens_by_tokenizer.get(budget.tokenizer, 0) > budget.max_tokens]
            if over:
                raise ChunkingError(f"chunks {over} have more than {budget.max_tokens} tokens of {budget.tokenizer}")
        return found

    # what is built once

    def _huggingface(self, name: str, max_tokens: int) -> Docling:
        with self._lock:
            if name not in self._loaded:
                auto = import_module("transformers").AutoTokenizer
                self._loaded[name] = pretrained(auto, name, self._cache)
            tokenizer = self._loaded[name]
        huggingface = import_module("docling_core.transforms.chunker.tokenizer.huggingface")
        return huggingface.HuggingFaceTokenizer(tokenizer=tokenizer, max_tokens=max_tokens)

    def _ready(self, parameters: ChunkingParameters) -> Docling:
        if not self.available():
            raise ChunkerUnavailable(MISSING)
        key = parameters.fingerprint
        with self._lock:
            if key in self._chunkers:
                return self._chunkers[key]
        try:
            built = self._build(parameters)
        except Exception as error:
            raise ChunkerUnavailable(f"the chunker can't be loaded: {type(error).__name__}: {error}".strip()) from error
        with self._lock:
            return self._chunkers.setdefault(key, built)

    def _tokenizers(self, parameters: ChunkingParameters) -> tuple[Docling, dict[str, Docling]]:
        """The tokenizer the chunker cuts with and, with `fit` (feature 062), each of its parts by name: then the
        chunker's is their composite, each with its budget."""
        if not parameters.fit:
            return self._factory(parameters.tokenizer, parameters.max_tokens or _UNLIMITED), {}
        parts = {b.tokenizer: self._factory(b.tokenizer, b.max_tokens) for b in parameters.fit}
        return fit_tokenizer(parts, {b.tokenizer: b.max_tokens for b in parameters.fit}), parts

    def _build(self, parameters: ChunkingParameters) -> Docling:
        tokenizer, parts = self._tokenizers(parameters)
        provider = _serializer_provider()
        fixed = CHUNKING_FIXED
        if parameters.chunker is DoclingChunker.HYBRID:
            hybrid = import_module("docling_core.transforms.chunker.hybrid_chunker")
            chunker = hybrid.HybridChunker(
                tokenizer=tokenizer,
                merge_peers=bool(parameters.merge_peers),
                repeat_table_header=fixed.repeat_table_header,
                always_emit_headings=fixed.always_emit_headings,
                serializer_provider=provider,
            )
        elif parameters.chunker is DoclingChunker.HIERARCHICAL:
            hierarchical = import_module("docling_core.transforms.chunker.hierarchical_chunker")
            chunker = hierarchical.HierarchicalChunker(
                merge_list_items=fixed.merge_list_items,
                always_emit_headings=fixed.always_emit_headings,
                serializer_provider=provider,
            )
        else:
            page = import_module("docling_core.transforms.chunker.page_chunker")
            chunker = page.PageChunker(serializer_provider=provider)
        return _Counting(chunker, tokenizer, parts)

    @staticmethod
    def _chunk(index: int, chunk: Docling, chunker: "_Counting") -> Chunk:
        contextualized = str(chunker.chunker.contextualize(chunk=chunk))
        pages = {prov.page_no for item in chunk.meta.doc_items for prov in (getattr(item, "prov", None) or [])}
        return Chunk(
            index=index,
            text=str(chunk.text),
            contextualized_text=contextualized,
            headings=[str(h) for h in getattr(chunk.meta, "headings", None) or []],
            pages=sorted(int(p) for p in pages),
            tokens=chunker.first(contextualized),
            tokens_by_tokenizer=chunker.each(contextualized),
        )


class _Counting:
    """A docling-core chunker with the tokenizer that counts its chunks (and, with fit, each of its parts)."""

    def __init__(self, chunker: Docling, tokenizer: Docling, parts: dict[str, Docling] | None = None) -> None:
        self.chunker, self.tokenizer = chunker, tokenizer
        self._parts = parts or {}

    def chunk(self, dl_doc: Docling) -> Docling:
        return self.chunker.chunk(dl_doc=dl_doc)

    def first(self, text: str) -> int:
        """The tokens of `text`: with fit (feature 062), those of its first tokenizer."""
        counter = next(iter(self._parts.values()), self.tokenizer)
        return int(counter.count_tokens(text))

    def each(self, text: str) -> dict[str, int]:
        """With fit, each tokenizer's tokens of `text`; empty without it."""
        return {name: int(part.count_tokens(text)) for name, part in self._parts.items()}


def fit_tokenizer(parts: dict[str, Docling], budgets: dict[str, int]) -> Docling:
    """A docling-core BaseTokenizer over several (feature 062): its count is fitted_count of theirs, which is at most
    min(budgets) exactly when every tokenizer is within its budget, so a chunk cut to it fits each of them. semchunk
    (HybridChunker's splitter of long texts) gets that count as its token counter."""
    base = import_module("docling_core.transforms.chunker.tokenizer.base").BaseTokenizer
    names = list(parts)
    smallest = min(budgets.values())

    def count(text: str) -> int:
        return fitted_count([int(parts[n].count_tokens(text)) for n in names], [budgets[n] for n in names])

    fitted = type(
        "FitTokenizer",
        (base,),
        {
            "count_tokens": lambda self, text: count(text),
            "get_max_tokens": lambda self: smallest,
            "get_tokenizer": lambda self: count,
        },
    )
    return fitted()


def _serializer_provider() -> Docling:
    """docling-core's chunking serializer (tables as triplets) with CHUNKING_FIXED: only the body layer, no formatting
    marks, hyperlinks kept, pictures only with their caption."""
    hierarchical = import_module("docling_core.transforms.chunker.hierarchical_chunker")
    markdown = import_module("docling_core.transforms.serializer.markdown")
    doc = import_module("docling_core.types.doc")
    fixed = CHUNKING_FIXED
    params = markdown.MarkdownParams(
        layers={doc.ContentLayer(layer) for layer in fixed.layers},
        include_formatting=fixed.formatting,
        include_hyperlinks=fixed.hyperlinks,
        image_mode=doc.ImageRefMode.PLACEHOLDER,
        image_placeholder="",
        escape_underscores=False,
        escape_html=False,
    )

    def get_serializer(self: Docling, doc: Docling) -> Docling:
        return hierarchical.ChunkingDocSerializer(doc=doc, params=params)

    provider: Docling = type(
        "FixedChunkingSerializerProvider",
        (hierarchical.ChunkingSerializerProvider,),
        {"get_serializer": get_serializer},
    )
    return provider()
