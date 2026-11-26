"""What the pipeline keeps in the graph (through data), one TypedDict per shape, as chunking's models/stored.py.

Neo4j only stores simple values and homogeneous lists: what is nested (stages, cursor, iterations...) goes as JSON
text. The keys are the stored property names (Spanish); a missing optional one is simply not written.
"""

from typing import NotRequired, TypedDict


class TemplateProperties(TypedDict):
    """PIPELINE."""

    nombre: str
    descripcion: str
    etapas: str  # JSON: the stages
    predefinida: bool
    creado_en: str
    modificado_en: str


class RunProperties(TypedDict):
    """PIPE_CORRIDA. The run is read back from here alone; the iteration and event nodes are for the graph."""

    nombre: str
    plantilla: str  # template id
    plantilla_copia: str  # JSON: the template as it was when the run was created
    estado: str
    archivos: NotRequired[str]  # JSON: the selection
    parametros: str  # JSON
    cursor: str  # JSON
    artefactos: str  # JSON
    iteraciones: str  # JSON
    registros: str  # JSON
    eventos: str  # JSON
    espera: NotRequired[str]  # JSON
    creado_en: str
    iniciado_en: NotRequired[str]
    terminado_en: NotRequired[str]
    error: NotRequired[str]
    etapa: NotRequired[str]  # the id of the stage at the cursor, for reading the graph
    actor: NotRequired[str]  # who it waits for
    tamano_parte: NotRequired[int]  # feature 056: the size of its parts
    partes: NotRequired[str]  # JSON: its parts (sha256s, status, what each gave)


class IterationProperties(TypedDict):
    """PIPE_ITERACION, id `<run>:<cycle>:<n>`. In the laboratory the score is of the trio (chunking + embeddings
    + llm, features 044 and 050): it lives here, not on either experiment."""

    corrida: str
    etapa: str
    indice: int
    estado: str
    configuracion: str  # JSON
    artefactos: str  # JSON
    experimentos: list[str]  # chunking experiments (PIPE_USA)
    experimentos_embeddings: list[str]
    iniciado_en: str
    config_llm: NotRequired[str]  # JSON: the llm configuration it tries (feature 050), if any
    reutiliza: NotRequired[int]  # the iteration whose experiments it reuses (a retry that only changed the llm)
    puntuacion: NotRequired[float]  # the score's `score`
    criterios: NotRequired[str]  # JSON: its `criteria`
    autor: NotRequired[str]
    comentario: NotRequired[str]
    puntuacion_completa: NotRequired[str]  # JSON: the score as the actor sent it
    terminado_en: NotRequired[str]


class EventProperties(TypedDict):
    """PIPE_EVENTO, id `<run>:e<n>`."""

    corrida: str
    indice: int
    actor: str
    tipo: str
    detalle: str  # JSON
    creado_en: str
