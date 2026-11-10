"""EmbeddingsClient: the contract of feature 048 with the embeddings module.

    POST {embeddings}/vectors {texts, model?, max_tokens?}   → {model, max_tokens, dimensions, index, experiment_index,
                                                                vectors}: a vector per text (the question, the pieces
                                                                of an attached document), with the active model
    GET  {embeddings}/experiments/{id}                        → {id, status, config: {model, max_tokens}, ...}

Network, timeout, 5xx or a route that isn't there: EmbeddingsDown (503); a 4xx (a model it no longer serves):
InvalidQuestion (422).
"""

from collections.abc import Sequence

import httpx

from common.http import BaseHttpClient, ErrorPolicy, segment
from consultas.models import EmbeddingsDown, EmbeddingsExperiment, InvalidQuestion, QuestionVector, TextVectors

from . import mappers as to

EMBEDDINGS_ERRORS = ErrorPolicy("embeddings", EmbeddingsDown, InvalidQuestion)


class EmbeddingsClient(BaseHttpClient):
    """`path`: embeddings' prefix in the server (/embeddings)."""

    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, path, EMBEDDINGS_ERRORS)

    def question(self, text: str, model: str | None = None, max_tokens: int | None = None) -> QuestionVector:
        body: dict[str, object] = {"texts": [text]}
        if model is not None:
            body["model"] = model
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        response = self._request("POST", "/vectors", body=body)
        if response is None:
            raise EmbeddingsDown(f"it has no {self._path}/vectors route")
        return to.question_vector(self._json(response), EmbeddingsDown)

    def texts(self, texts: Sequence[str], model: str, max_tokens: int) -> TextVectors:
        body = {"texts": list(texts), "model": model, "max_tokens": max_tokens}
        response = self._request("POST", "/vectors", body=body)
        if response is None:
            raise EmbeddingsDown(f"it has no {self._path}/vectors route")
        return to.text_vectors(self._json(response), len(texts), EmbeddingsDown)

    def experiment(self, id: str) -> EmbeddingsExperiment | None:
        found = self._get(f"/experiments/{segment(id)}")
        return None if found is None else to.experiment(found, EmbeddingsDown)
