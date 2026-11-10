"""What is stored in the graph: one TypedDict per shape, used by who writes it (domain/) and by who reads it (the
mappers), so that a misspelled key is a mypy error. The keys are Neo4j property names: Spanish.

Since feature 055 a vector's property and a document's fingerprint carry the model in their name
(`embedding_<model>_<dim>`, `huella_embedding_<model>_<dim>`: domain/indexes.py builds them), so they can't be keys of
a TypedDict: the domain puts them next to the fixed ones."""

from typing import TypedDict

# This module's own properties, written with merge on the nodes chunking created (the text stays as it is).


class EmbedProperties(TypedDict):
    """An EXP_EMBED (feature 055): the vector one embeddings experiment calculated for one EXP_CHUNK, besides the
    vector itself (`embedding_<model>_<dim>`)."""

    modelo: str
    version_embedding: int


class DocumentVectors(TypedDict):
    """On the official JSON, besides `huella_embedding_<model>_<dim>` (what that model's vectors were calculated
    from) and `limite_tokens_embedding_<model>_<dim>` (the limit the run used): when it was last embedded."""

    embebido_en: str


class ConfigProperties(TypedDict):
    """This module's CONFIG_OFICIAL node."""

    modulo: str  # "embeddings"
    modelo: str
    max_tokens: int
    origen: str  # ConfigOrigin
    experimento: str | None
    modificado_en: str


class RunProperties(TypedDict):
    """A CORRIDA_EMBEDDINGS or EXP_EMBEDDINGS node: the run as GET answers it (`detalle`, JSON). An experiment is
    linked to its chunking experiment (EXP_USA)."""

    estado: str
    inicio: str
    detalle: str
