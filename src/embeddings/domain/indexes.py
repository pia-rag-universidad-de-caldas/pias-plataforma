"""The names of a model's vectors (feature 055): its property, its indexes and its fingerprint key. Each name says
which model and dimensions it holds, so a new model or dimension is a new property and a new index by itself, next to
the others (Neo4j admits one vector index per label and property)."""

import re

from embeddings.config import MODELS
from embeddings.models import GraphLabel, VectorIndexSpec

PROPERTY_PREFIX = "embedding_"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _short(model: str, dimensions: int) -> str:
    """<model without its owner>_<dimensions>: paraphrase_multilingual_minilm_l12_v2_384."""
    return f"{_slug(model.rsplit('/', 1)[-1])}_{dimensions}"


def property_for(model: str, dimensions: int) -> str:
    """embedding_<model>_<dim>: where that model's vectors live, on FRAGMENTOS and on EXP_EMBED."""
    return PROPERTY_PREFIX + _short(model, dimensions)


def index_for(label: str, property: str) -> str:
    """vec_<label>_<model>_<dim>, the index of a vector property on a label: vec_fragmentos_..._384 on
    FRAGMENTOS.embedding_..._384, vec_exp_embed_..._384 on EXP_EMBED.embedding_..._384."""
    return f"vec_{_slug(label)}_{property.removeprefix(PROPERTY_PREFIX)}"


def index_name(label: str, model: str, dimensions: int) -> str:
    return index_for(label, property_for(model, dimensions))


def vector_property(model: str) -> str:
    """The property of a served model."""
    return property_for(model, MODELS[model].dimensions)


def fingerprint_key(model: str) -> str:
    """huella_embedding_<model>_<dim>: on the official JSON, what that model's vectors were calculated from."""
    return "huella_" + vector_property(model)


def limit_key(model: str) -> str:
    """limite_tokens_embedding_<model>_<dim>: on the official JSON, the limit that model's run used."""
    return "limite_tokens_" + vector_property(model)


def vector_index(label: GraphLabel, model: str) -> VectorIndexSpec:
    """The index of `model` over the nodes of `label` (FRAGMENTOS or EXP_EMBED)."""
    dimensions = MODELS[model].dimensions
    property = property_for(model, dimensions)
    return VectorIndexSpec(index_for(label.value, property), label.value, property, dimensions)
