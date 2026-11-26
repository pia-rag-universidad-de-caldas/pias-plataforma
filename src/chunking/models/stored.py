"""What chunking stores in (and reads from) the graph (features 027 and 043): one TypedDict per shape, used by both
sides, the domain that builds the batches and the mappers that read them back (adapters/data/), so that a misspelled
key is a mypy error on either side. A TypedDict doesn't check anything at runtime: the mappers still check each value
they read.

Property names and values are stored in Neo4j: they stay in Spanish.
"""

from typing import NotRequired, TypedDict

# What parsing writes on a JSON node (feature 042) and chunking reads: never written here.


class ParsedJsonProperties(TypedDict):
    sha256: str
    estado: str  # parseado, parcial, error
    fingerprint_parseo: str
    documento: str  # base64(gzip(DoclingDocument JSON))


# What chunking writes on a JSON node (merge: only these; the parse's stay as they are).


class ChunkingParametersProperties(TypedDict):
    chunker: str  # DoclingChunker
    tokenizador: str
    max_tokens: int | None
    fusionar_vecinos: bool | None
    version_chunking: int
    docling_core: str
    fit: str | None  # feature 062: [{tokenizer, max_tokens}] as JSON; None without fit


class JsonChunkingProperties(ChunkingParametersProperties):
    estado_chunking: str  # fragmentado
    error_chunking: None
    huella_chunking: str  # chunked_fingerprint: parameters + parse
    config_chunking: str  # ChunkingParameters.fingerprint (feature 045: data counts what is missing with it)
    parseo_chunkeado: str  # the fingerprint_parseo it was chunked over
    fragmentado_en: str  # ISO
    fragmentos: int
    experimento_config: str | None  # the experiment the configuration came from, if it came from one


class JsonChunkingMark(TypedDict):
    """What data counts with, on a JSON chunked before feature 045 with the same configuration (its chunks stay)."""

    config_chunking: str
    parseo_chunkeado: str


class JsonChunkingFailure(TypedDict, total=False):
    """A failure: only the error (and, without chunks, the state); chunks and parameters that were there stay."""

    estado_chunking: str  # error
    error_chunking: str


class SectionProperties(TypedDict):
    orden: int
    encabezados: list[str]


class ChunkProperties(TypedDict):
    """A FRAGMENTOS node (and an EXP_CHUNK, the same shape)."""

    indice: int
    texto: str
    texto_contextualizado: str
    encabezados: list[str]
    paginas: list[int]
    tokens: int
    tokens_por_tokenizador: NotRequired[str]  # feature 062, with fit: {tokenizer: tokens} as JSON


# Experiments (features 043 and 055 part b): (:EXPERIMENTO)-[:EXP_TIENE_DOCUMENTO]->(:EXP_DOCUMENTO)-[:EXP_DE]->(:JSON),
# (:EXP_DOCUMENTO)-[:EXP_TIENE_SECCION]->(:EXP_SECCION)-[:EXP_TIENE_CHUNK]->(:EXP_CHUNK)


class ExperimentProperties(TypedDict, total=False):
    """An EXPERIMENTO; written in parts (created, started, finished), so every key is optional. The request, the
    progress and the results go as JSON text."""

    nombre: str
    descripcion: str
    creado_en: str
    iniciado_en: str  # when its turn came: it may have been queued since creado_en
    estado: str  # ExperimentStatus
    progreso: str  # ExperimentProgress as JSON
    documentos: str  # the sha256s asked for (or from_experiment, or all: feature 059), as JSON
    chunking: str  # ChunkingParameters as JSON
    selecciones: str  # feature 062: [{at, documents, kind}] as JSON, one per creation and POST .../documents
    terminado_en: str | None  # None while it runs again (resume)
    resultados: str  # ExperimentResults as JSON
    error: str | None


class ExperimentDocumentProperties(TypedDict):
    """An EXP_DOCUMENTO (feature 055 part b; before, the EXP_USA relationship EXPERIMENTO → JSON): what the experiment
    did with the document."""

    sha256: str
    estado: str  # fragmentado or error
    error: str | None
    chunks: int
    tokens: int
    duracion: float
    tokens_por_chunk: list[int]  # feature 045: the results of a resumed experiment are counted over every document


class ExperimentSectionProperties(SectionProperties):
    """An EXP_SECCION: a heading path of one document in one experiment."""

    sha256: str


# The active configuration (feature 043): one CONFIG_OFICIAL node.


class ConfigProperties(TypedDict):
    chunker: str
    tokenizador: str | None
    max_tokens: int | None
    fusionar_vecinos: bool | None
    fit: str | None  # feature 062: [{tokenizer, max_tokens}] as JSON; None without fit
    origen: str  # ConfigOrigin
    experimento: str | None
    modificado_en: str


# The record of POST /runs (feature 045): a CORRIDA_CHUNKING.


class RunProperties(TypedDict, total=False):
    estado: str  # RunStatus
    pedido_en: str
    inicio: str | None
    fin: str | None
    simulacion: bool
    parametros: str  # ChunkingParameters as JSON
    experimento_config: str | None
    documentos: str  # the sha256s it goes over (frozen), as JSON
    congelada: bool  # false: it takes what is missing when its turn comes
    pagina: int | None  # of what is missing
    por_pagina: int | None
    progreso: str  # RunProgress as JSON
    fallos: str  # DocumentFailure as JSON
    fragmentados: str  # the sha256s chunked, as JSON
    error: str | None
    retomada: int  # how many times it was resumed
