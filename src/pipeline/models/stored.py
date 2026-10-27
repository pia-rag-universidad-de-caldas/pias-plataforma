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


class IterationProperties(TypedDict):
    """PIPE_ITERACION, id `<run>:<cycle>:<n>`."""

    corrida: str
    etapa: str
    indice: int
    estado: str
    configuracion: str  # JSON
    artefactos: str  # JSON
    experimentos: list[str]
    iniciado_en: str
    puntuacion: NotRequired[str]  # JSON
    terminado_en: NotRequired[str]


class EventProperties(TypedDict):
    """PIPE_EVENTO, id `<run>:e<n>`."""

    corrida: str
    indice: int
    actor: str
    tipo: str
    detalle: str  # JSON
    creado_en: str
