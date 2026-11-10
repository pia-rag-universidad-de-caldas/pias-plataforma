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


class CitationProperties(TypedDict):
    """The RESPONDIDA_CON relationship (CONSULTA → a chunk)."""

    puntaje: float
    orden: int  # 1 is the best: the number the answer cites it with


class ConfigProperties(TypedDict):
    """This module's CONFIG_OFICIAL node."""

    modulo: str  # "consultas"
    k: int
    min_score: float
    prompt: str
    historia: int
    origen: str  # ConfigOrigin
    modificado_en: str
