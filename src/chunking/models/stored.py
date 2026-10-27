"""What chunking stores in the graph (feature 027): one TypedDict per shape it writes, used by both sides, the domain
that builds the batches (Hierarchy, ExperimentGraph) and the mappers that read them back (adapters/data/), so that a
misspelled key is a mypy error on either side. A TypedDict doesn't check anything at runtime: the mappers still check
each value they read.

Property names and values are stored in Neo4j: they stay in Spanish.
"""

from typing import TypedDict

# Production (feature 023): (:PIAA)-[:ES]->(:JSON)-[:TIENE_SECCION]->(:SECCION)-[:TIENE_FRAGMENTO]->(:FRAGMENTOS)


class ParametersProperties(TypedDict):
    """The chunking parameters a JSON node was chunked with (ChunkingParameters)."""

    tokenizador: str
    max_tokens: int
    fusionar_vecinos: bool
    repetir_encabezado_tabla: bool
    estructura_tablas: bool
    modo_tablas: str  # TableMode
    docling: str


class JsonProperties(ParametersProperties):
    """A JSON node: the document, its parameters and how its chunking went."""

    origen: str
    destino: str
    nombre: str
    tipo: str
    anio: int | None
    codigo: str | None
    sha256: str
    fingerprint: str  # of the parameters
    estado: str  # DocumentStatus
    error: str | None
    fragmentado_en: str  # ISO
    fragmentos: int


class SectionProperties(TypedDict):
    orden: int
    encabezados: list[str]


class ChunkProperties(TypedDict):
    """A FRAGMENTOS node."""

    indice: int
    texto: str
    texto_contextualizado: str
    encabezados: list[str]
    paginas: list[int]
    tokens: int


# Experiments (feature 025): EXPERIMENTO, EXP_DOCUMENTO, EXP_SECCION, EXP_CHUNK, EXP_PUNTUACION


class ExperimentProperties(TypedDict, total=False):
    """An EXPERIMENTO; written in parts (created, progress, finished), so every key is optional. The request, the
    progress and the results go as JSON text."""

    nombre: str
    descripcion: str
    creado_en: str
    estado: str  # ExperimentStatus
    progreso: str  # ExperimentProgress as JSON
    archivos: str  # the files asked for, as JSON
    conversion: str  # ConversionParameters as JSON
    plan: str  # as JSON
    terminado_en: str
    resultados: str  # ExperimentResults as JSON
    error: str | None


CONVERTED = "convertido"  # EXP_DOCUMENTO.estado of a conversion that can be reused
CONVERSION_FAILED = "error"


class ConversionProperties(TypedDict):
    """An EXP_DOCUMENTO: a file, its conversion (shared by every experiment with the same parameters) and with what."""

    sha256: str
    origen: str
    destino: str
    nombre: str
    tipo: str
    anio: int | None
    codigo: str | None
    conversion: str  # ConversionParameters as JSON
    fingerprint_conversion: str
    docling: str
    estado: str  # CONVERTED or CONVERSION_FAILED
    error: str | None
    contenido: str | None  # ConvertedDocument.to_json
    secciones: int
    duracion_conversion: float
    convertido_en: str


class ExperimentUseProperties(TypedDict):
    """The EXP_USA relationship (EXPERIMENTO → EXP_DOCUMENTO): what the experiment did with the document."""

    sha256: str
    origen: str
    nombre: str
    codigo: str | None
    reutilizado: bool
    estado: str  # DocumentStatus
    error: str | None
    secciones: int
    chunks: int
    duracion_chunking: float


class ExperimentSectionProperties(TypedDict):
    """An EXP_SECCION: how one section of a document was treated in one experiment."""

    indice: int
    titulo: str
    nivel: int
    paginas: list[int]
    regla: str  # rule_name
    estrategia: str  # ChunkingStrategy
    parametros: str  # the strategy's parameters as JSON
    chunks: int
    tokens: int


class ExperimentChunkProperties(TypedDict):
    """An EXP_CHUNK."""

    indice: int
    texto: str
    encabezados: list[str]
    paginas: list[int]
    tokens: int


class ScoreProperties(TypedDict):
    """An EXP_PUNTUACION."""

    puntuacion: str  # the score's id within its experiment
    experimento: str
    criterios: str  # name → value, as JSON
    autor: str | None
    comentario: str | None
    objetivo: str | None
    creado_en: str
    modificado_en: str


# Official JSON (feature 028): promoted from an approved experiment.
# (:PIAA)-[:ES]->(:JSON)-[:VIENE_DE]->(:EXP_DOCUMENTO); its chunks promoted later go under it as SECCION/FRAGMENTOS,
# like production (023).


class OfficialJsonProperties(TypedDict):
    """A JSON node promoted from a conversion: the file, the conversion it came from and its content."""

    sha256: str
    origen: str
    destino: str
    nombre: str
    tipo: str
    anio: int | None
    codigo: str | None
    contenido: str  # ConvertedDocument.to_json
    conversion: str  # ConversionParameters as JSON
    fingerprint_conversion: str
    docling: str
    secciones: int
    estado: str  # DocumentStatus.CONVERTED
    error: None
    convertido_en: str
    oficializado_en: str
    experimento_conversion: str  # the experiment it was approved in


class OfficialChunksProperties(TypedDict):
    """What promoting its chunks sets on an official JSON (merge: the rest is kept)."""

    estado: str  # DocumentStatus.CHUNKED
    fragmentos: int
    fragmentado_en: str
    experimento_chunks: str


class OfficialSectionProperties(SectionProperties):
    """A SECCION promoted from an EXP_SECCION: with the rule and strategy it was cut with."""

    titulo: str
    paginas: list[int]
    regla: str  # rule_name
    estrategia: str
    parametros: str  # as JSON


DEFAULT_RULE = "default"  # EXP_SECCION.regla (and the keys of `by_rule`) of the sections no rule took


def rule_name(rule: int | None) -> str:
    """How the rule that took a section is stored: its index, or "default" for the plan's default."""
    return DEFAULT_RULE if rule is None else str(rule)


def rule_index(name: object) -> int | None:
    """Back from rule_name; "default" (or anything that isn't an index) is the plan's default."""
    return int(name) if isinstance(name, str) and name.isdigit() else None
