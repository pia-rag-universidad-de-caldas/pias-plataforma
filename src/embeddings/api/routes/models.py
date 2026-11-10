"""GET /models: the embedding models of the project, with their token limits (the pipeline fits chunking to them) and
how many official documents have their vectors; DELETE /models/{name}/vectors drops a model's official vectors once
another one is active (feature 055: models change without cutting the chat)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from embeddings.api.dependencies import Config, Source, Vectors
from embeddings.api.responses import DOWN, INVALID, error
from embeddings.api.schemas import ServedModel
from embeddings.config import DEFAULT_MODEL, MODELS
from embeddings.domain import ActiveModel, documents_per_model, drop_vectors, resolve
from embeddings.models import DocumentError, DroppedVectors, UpstreamDown

router = APIRouter(tags=["models"])


@router.get("/models")
def list_models(
    source: Source,
    documents: Annotated[
        bool, Query(description="count each model's official documents (reads every JSON: slow)")
    ] = False,
) -> list[ServedModel]:
    """Both limits count the model's special tokens: a chunk of chunking may have the limit minus 2. With
    `documents=true`, how many official documents have each model's vectors (None if data doesn't answer: the models
    are answered anyway); without it, None, and data isn't asked (the pipeline asks for the models at every check)."""
    counts: dict[str, int] | None = None
    if documents:
        try:
            counts = documents_per_model(source)
        except (UpstreamDown, DocumentError):
            counts = None
    return [
        ServedModel(
            name,
            spec.dimensions,
            spec.default_tokens,
            spec.max_tokens,
            name == DEFAULT_MODEL,
            None if counts is None else counts[name],
        )
        for name, spec in MODELS.items()
    ]


@router.delete(
    "/models/{name:path}/vectors",
    responses=DOWN | INVALID | error(409, "it is the active model: the chat searches its vectors"),
)
def drop_model_vectors(source: Source, vectors: Vectors, config: Config, name: str) -> DroppedVectors:
    """Removes that model's official vectors: its fingerprint from every JSON, its FRAGMENTOS index and its property.
    Never the active model's (PUT /config another one first); the experiments' vectors (EXP_EMBED) stay."""
    try:
        return drop_vectors(source, vectors, name, resolve(config))
    except ActiveModel as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
