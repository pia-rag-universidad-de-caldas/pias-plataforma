"""The real model (feature 046): 384 dimensions, norm 1, tokens with the special ones, and a max_tokens of MODELS that
the model admits. Skipped without the `embed` extra or without the model in MODEL_CACHE (it is never downloaded
here: POST /embeddings/runs does it the first time)."""

import math
from pathlib import Path

import pytest

from embeddings.adapters import LocalModels
from embeddings.config import DEFAULT_MODEL, MODEL_CACHE, MODELS

pytestmark = pytest.mark.embed
CACHE = Path(__file__).resolve().parents[3] / MODEL_CACHE


@pytest.fixture(scope="module")
def models() -> LocalModels:
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    if not (CACHE / f"models--{DEFAULT_MODEL.replace('/', '--')}").is_dir():
        pytest.skip(f"{DEFAULT_MODEL} isn't in {CACHE}")
    return LocalModels(str(CACHE))


def test_a_vector_has_the_dimensions_of_the_model_and_norm_one(models: LocalModels) -> None:
    [vector] = models.embed(DEFAULT_MODEL, ["¿Qué temas se ven en Bases de Datos?"], 128)
    assert len(vector) == MODELS[DEFAULT_MODEL].dimensions
    assert math.isclose(math.fsum(v * v for v in vector), 1.0, rel_tol=1e-4)


def test_tokens_count_the_special_ones(models: LocalModels) -> None:
    assert models.tokens(DEFAULT_MODEL, "") == 2


def test_the_largest_limit_of_models_is_one_the_model_admits(models: LocalModels) -> None:
    limit = MODELS[DEFAULT_MODEL].max_tokens
    [vector] = models.embed(DEFAULT_MODEL, ["palabra " * (limit * 2)], limit)  # cut at the limit, not broken
    assert len(vector) == MODELS[DEFAULT_MODEL].dimensions
