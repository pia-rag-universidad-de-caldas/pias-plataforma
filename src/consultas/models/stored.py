"""What is stored in the graph: one TypedDict per shape, used by who writes it (domain/) and by who reads it (the
mappers), so that a misspelled key is a mypy error. The keys are Neo4j property names: Spanish."""

from typing import NotRequired, TypedDict


class ChatProperties(TypedDict, total=False):
    """A CHAT: written whole when it is created; then only `modificado_en` changes (merge)."""

    titulo: str
    creado_en: str
    modificado_en: str
    laboratorio: bool  # its questions were asked against an embeddings experiment


class QuestionProperties(TypedDict):
    """A CONSULTA."""

    pregunta: str
    respuesta: str
    modelo_llm: str | None  # None: the LLM wasn't called (nothing passed min_score)
    modelo_embedding: str
    k: int
    creado_en: str
    segundos: float  # search and answer
    laboratorio: bool
    experimento_embedding: str | None  # the embeddings experiment asked (laboratory)
    encontrada: bool  # some chunk passed min_score
    # With attachments (phase 2) only: their names and MIME types, never their content.
    adjuntos: NotRequired[list[str]]
    tipos_adjuntos: NotRequired[list[str]]
    caracteres_busqueda: NotRequired[int]  # of the texts the attachments searched with (pieces, descriptions)
    trozos_busqueda: NotRequired[int]  # how many texts they were
    documentos_curso: NotRequired[list[str]]  # the documents of the courses it named: only theirs searched (057)
    # A panel of a comparison (feature 060) only: what shows it again as it was answered.
    segundos_busqueda: NotRequired[float]
    segundos_respuesta: NotRequired[float]
    uso_adjuntos: NotRequired[str]  # JSON: what each attachment searched with (AttachmentUse)
    cursos: NotRequired[str]  # JSON: the courses it named (CourseMatch)


class CitationProperties(TypedDict):
    """The RESPONDIDA_CON relationship (CONSULTA → a chunk)."""

    puntaje: float
    orden: int  # 1 is the best: the number the answer cites it with
    # In a comparison (feature 060) only: what the search said of the chunk, to show the source as it was found.
    sha256: NotRequired[str]
    origen: NotRequired[str]
    codigo: NotRequired[str]
    actividad: NotRequired[str]


class ConfigProperties(TypedDict):
    """This module's CONFIG_OFICIAL node."""

    modulo: str  # "consultas"
    k: int
    min_score: float
    prompt: str
    historia: int
    origen: str  # ConfigOrigin
    modificado_en: str


class ComparisonProperties(TypedDict):
    """A COMPARACION (feature 060)."""

    pregunta: str
    creado_en: str
    paneles: str  # JSON: a PanelProperties per panel, in order
    laboratorio: bool  # some panel asked an embeddings experiment


class ComparedProperties(TypedDict):
    """The COMPARA relationship (COMPARACION → the CONSULTA of a panel)."""

    panel: int  # its index, from 0
    etiqueta: str


class TargetProperties(TypedDict, total=False):
    """Where a panel searched: one of the two, or the panel has none (the official chunks with the active model)."""

    experimento_embedding: str
    modelo_embedding: str


class LlmProperties(TypedDict, total=False):
    """What a panel asked of the LLM: only what came."""

    modelo: str
    temperatura: float
    num_ctx: int
    max_tokens: int


class PanelProperties(TypedDict):
    """A panel inside the `paneles` JSON of a COMPARACION: its configuration and how it went."""

    indice: int
    etiqueta: str
    destino: TargetProperties | None
    llm: LlmProperties
    k: int | None
    estado: str  # PanelStatus
    error: str | None
    consulta: str | None  # its CONSULTA; None if it failed (a failed panel stores none)
    modelo_llm: str | None  # the LLM that answered; None if it wasn't called
