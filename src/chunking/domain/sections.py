"""What the official graph and the experiments share (feature 043): chunks grouped by their headings, and the stored
shapes of the parameters, of a section and of a chunk."""

import json

from chunking.models import (
    Chunk,
    ChunkingParameters,
    ChunkingParametersProperties,
    ChunkProperties,
    Section,
    fit_json,
)

type HeadingPath = tuple[str, ...]


def sections(chunks: list[Chunk]) -> list[Section]:
    """One section per distinct heading path of `chunks`, by first appearance (those without headings share one)."""
    paths: dict[HeadingPath, int] = {}
    for chunk in chunks:
        paths.setdefault(tuple(chunk.headings), len(paths))
    return [Section(order, list(path)) for path, order in paths.items()]


def parameters_properties(parameters: ChunkingParameters) -> ChunkingParametersProperties:
    return {
        "chunker": parameters.chunker.value,
        "tokenizador": parameters.tokenizer,
        "max_tokens": parameters.max_tokens,
        "fusionar_vecinos": parameters.merge_peers,
        "version_chunking": parameters.chunking_version,
        "docling_core": parameters.docling_version,
        "fit": json.dumps(fit_json(parameters.fit)) if parameters.fit else None,
    }


def chunk_properties(chunk: Chunk) -> ChunkProperties:
    properties: ChunkProperties = {
        "indice": chunk.index,
        "texto": chunk.text,
        "texto_contextualizado": chunk.contextualized_text,
        "encabezados": chunk.headings,
        "paginas": chunk.pages,
        "tokens": chunk.tokens,
    }
    if chunk.tokens_by_tokenizer:
        properties["tokens_por_tokenizador"] = json.dumps(chunk.tokens_by_tokenizer, sort_keys=True)
    return properties
