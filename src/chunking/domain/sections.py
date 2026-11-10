"""What the official graph and the experiments share (feature 043): chunks grouped by their headings, and the stored
shapes of the parameters, of a section and of a chunk."""

from chunking.models import (
    Chunk,
    ChunkingParameters,
    ChunkingParametersProperties,
    ChunkProperties,
    Section,
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
    }


def chunk_properties(chunk: Chunk) -> ChunkProperties:
    return {
        "indice": chunk.index,
        "texto": chunk.text,
        "texto_contextualizado": chunk.contextualized_text,
        "encabezados": chunk.headings,
        "paginas": chunk.pages,
        "tokens": chunk.tokens,
    }
