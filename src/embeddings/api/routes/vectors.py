"""POST /vectors: texts → vectors, with the active configuration's model (feature 048). The search left this module: it
is consultas' (its own question, embedded here, then data's POST /data/vectors/search). The answer names the indexes
of that model, so whoever searches uses the index of the same model that embedded the question."""

from fastapi import APIRouter

from embeddings.api.dependencies import Config, Embedding
from embeddings.api.responses import DOWN, INVALID
from embeddings.api.schemas import NewVectors, TextVectors
from embeddings.config import MODELS
from embeddings.domain import queries, resolve, token_limit, vector_index
from embeddings.models import GraphLabel

router = APIRouter(tags=["vectors"])


@router.post("/vectors", responses=DOWN | INVALID)
def vectors(embedder: Embedding, config: Config, body: NewVectors) -> TextVectors:
    """One vector per text, in order. A text longer than max_tokens is cut (a question isn't a document: nothing
    fails). `model` (another served model, as an embeddings experiment's) replaces the active one only here; its limit
    is then the model's default unless `max_tokens` says another."""
    active = resolve(config)
    model = body.model or active.model
    asked = body.max_tokens if body.max_tokens is not None else (active.max_tokens if model == active.model else None)
    limit = token_limit(model, asked)  # 422 before loading anything
    found = embedder.embed(model, queries(model, list(body.texts)), limit)  # e5 reads `query: ` first
    return TextVectors(
        model=model,
        max_tokens=limit,
        dimensions=MODELS[model].dimensions,
        index=vector_index(GraphLabel.FRAGMENTOS, model).name,
        experiment_index=vector_index(GraphLabel.EXP_EMBED, model).name,
        vectors=found,
    )
