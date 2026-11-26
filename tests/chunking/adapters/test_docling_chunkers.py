"""DoclingChunkers (feature 043): docling-core's chunkers over a DoclingDocument built here and stored as parsing does,
with a tokenizer of words (no model is downloaded). Omitted without the `chunk` extra."""

import re
from collections.abc import Callable
from typing import Any

import pytest

from chunking.adapters.docling_chunkers import DoclingChunkers, encode
from chunking.config import TOKENIZERS
from chunking.domain import Parameters
from chunking.models import ChunkerUnavailable, ChunkingError, DoclingChunker, RequestedChunking, TokenBudget

pytestmark = pytest.mark.docling
type Docling = Any  # docling-core is untyped here: it may not be installed
SENTENCE = "Uno dos tres cuatro cinco seis siete ocho nueve diez "


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text))


@pytest.fixture(scope="module")
def doc() -> Docling:
    return pytest.importorskip("docling_core.types.doc")


@pytest.fixture(scope="module")
def words() -> Callable[[str, int], Docling]:
    """A docling-core tokenizer that counts words: (name, max_tokens) → tokenizer."""
    base = pytest.importorskip("docling_core.transforms.chunker.tokenizer.base").BaseTokenizer
    words = type(
        "Words",
        (base,),
        {
            "__annotations__": {"max_tokens": int},
            "count_tokens": lambda self, text: _words(text),
            "get_max_tokens": lambda self: self.max_tokens,
            "get_tokenizer": lambda self: _words,
        },
    )
    return lambda name, max_tokens: words(max_tokens=max_tokens)


@pytest.fixture(scope="module")
def stored(doc: Docling) -> str:
    """A title, a long paragraph, a page footer (furniture) and a table on page 2, stored as parsing stores it."""

    def prov(page: int) -> Docling:
        return doc.ProvenanceItem(page_no=page, bbox=doc.BoundingBox(l=0, t=0, r=1, b=1), charspan=(0, 1))

    document = doc.DoclingDocument(name="piaa")
    for page in (1, 2):  # a PDF converted by Docling always has its pages
        document.add_page(page_no=page, size=doc.Size(width=612, height=792))
    document.add_heading("Objetivos", level=1, prov=prov(1))
    document.add_text(label=doc.DocItemLabel.TEXT, text=SENTENCE * 5, prov=prov(1))
    document.add_text(
        label=doc.DocItemLabel.PAGE_FOOTER,
        text="Universidad de Caldas",
        prov=prov(1),
        content_layer=doc.ContentLayer.FURNITURE,
    )
    cells = [
        doc.TableCell(
            text=text,
            start_row_offset_idx=row,
            end_row_offset_idx=row + 1,
            start_col_offset_idx=col,
            end_col_offset_idx=col + 1,
            column_header=row == 0,
        )
        for row, values in enumerate([["Actividad", "Peso"], ["Parcial", "30"]])
        for col, text in enumerate(values)
    ]
    document.add_table(data=doc.TableData(num_rows=2, num_cols=2, table_cells=cells), prov=prov(2))
    return encode(document.model_dump_json())


def chunk(chunkers: DoclingChunkers, stored: str, asked: RequestedChunking) -> list[Docling]:
    return chunkers.chunk(stored, Parameters.resolve(asked, chunkers.version() or ""))


def test_hybrid_keeps_every_chunk_within_max_tokens(words: Docling, stored: str) -> None:
    found = chunk(DoclingChunkers(words), stored, RequestedChunking(DoclingChunker.HYBRID, max_tokens=20))
    assert len(found) > 1 and all(c.tokens <= 20 for c in found)
    assert all(c.contextualized_text.startswith("Objetivos") for c in found)  # the headings in front


def test_with_fit_every_chunk_fits_each_tokenizer_within_its_budget(words: Docling, stored: str) -> None:
    """Feature 062: one tokenizer counts words, the other counts one token per 3 characters (a denser vocabulary);
    the composite cuts so that each one stays within its own budget, and each count is kept."""
    base = pytest.importorskip("docling_core.transforms.chunker.tokenizer.base").BaseTokenizer

    def dense(text: str) -> int:
        return -(-len(text) // 3)

    characters = type(
        "Characters",
        (base,),
        {
            "__annotations__": {"max_tokens": int},
            "count_tokens": lambda self, text: dense(text),
            "get_max_tokens": lambda self: self.max_tokens,
            "get_tokenizer": lambda self: dense,
        },
    )
    mini, e5 = TOKENIZERS[0], "intfloat/multilingual-e5-base"

    def factory(name: str, max_tokens: int) -> Docling:
        return characters(max_tokens=max_tokens) if name == e5 else words(name, max_tokens)

    fit = (TokenBudget(mini, 20), TokenBudget(e5, 40))
    found = chunk(DoclingChunkers(factory), stored, RequestedChunking(fit=fit))
    assert len(found) > 1
    for c in found:
        assert c.tokens_by_tokenizer == {mini: _words(c.contextualized_text), e5: dense(c.contextualized_text)}
        assert c.tokens_by_tokenizer[mini] <= 20 and c.tokens_by_tokenizer[e5] <= 40
        assert c.tokens == c.tokens_by_tokenizer[mini]  # `tokens` is the first one's


def test_hierarchical_gives_one_chunk_per_element_with_its_pages(words: Docling, stored: str) -> None:
    found = chunk(DoclingChunkers(words), stored, RequestedChunking(DoclingChunker.HIERARCHICAL))
    assert [c.pages for c in found] == [[1], [2]]
    assert [c.index for c in found] == [0, 1] and found[0].headings == ["Objetivos"]


def test_page_gives_one_chunk_per_page(words: Docling, stored: str) -> None:
    found = chunk(DoclingChunkers(words), stored, RequestedChunking(DoclingChunker.PAGE))
    assert [c.pages for c in found] == [[1], [2]]


def test_tables_are_triplets_and_page_footers_are_left_out(words: Docling, stored: str) -> None:
    found = chunk(DoclingChunkers(words), stored, RequestedChunking(DoclingChunker.HIERARCHICAL))
    text = "\n".join(c.text for c in found)
    assert "Parcial, Peso = 30" in text and "Universidad de Caldas" not in text


def test_a_stored_document_that_isnt_one_fails_alone(words: Docling) -> None:
    chunkers = DoclingChunkers(words)
    with pytest.raises(ChunkingError, match="can't be read"):
        chunk(chunkers, "not base64!", RequestedChunking())
    with pytest.raises(ChunkingError, match="isn't a DoclingDocument"):
        chunk(chunkers, encode('{"name": 3}'), RequestedChunking())


def test_without_docling_core_nothing_is_chunked(words: Docling, stored: str, monkeypatch: pytest.MonkeyPatch) -> None:
    chunkers = DoclingChunkers(words)
    monkeypatch.setattr(DoclingChunkers, "available", lambda _: False)
    with pytest.raises(ChunkerUnavailable):
        chunk(chunkers, stored, RequestedChunking())


def test_a_tokenizer_that_cant_be_loaded_stops_everything(stored: str) -> None:
    def broken(name: str, max_tokens: int) -> Docling:
        raise OSError("offline")

    with pytest.raises(ChunkerUnavailable, match="offline"):
        chunk(DoclingChunkers(broken), stored, RequestedChunking())
