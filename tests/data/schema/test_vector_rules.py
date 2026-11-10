"""What a vector index may be: data's rules over what embeddings asks for."""

import pytest

from data.models import Label
from data.schema.vector_rules import MAX_DIMENSIONS, index_problems


def test_a_good_index_has_no_problems() -> None:
    assert index_problems("vec_fragmentos_minilm_384", Label.FRAGMENTOS, 384, "embedding_minilm_384") == []


@pytest.mark.parametrize("name", ["fragmentos", "vec_", "vec_Upper", "vec_x; DROP", "vec_" + "a" * 121])
def test_a_bad_name_is_a_problem(name: str) -> None:
    assert index_problems(name, Label.EXP_EMBED, 3, "embedding_x_3") != []


@pytest.mark.parametrize("dimensions", [0, MAX_DIMENSIONS + 1])
def test_dimensions_out_of_range_are_a_problem(dimensions: int) -> None:
    assert index_problems("vec_x", Label.FRAGMENTOS, dimensions, "embedding_x_3") != []


def test_only_chunks_have_vectors() -> None:
    assert index_problems("vec_x", Label.JSON, 3, "embedding_x_3") == [
        "only these labels have vectors: FRAGMENTOS or EXP_EMBED"
    ]


@pytest.mark.parametrize("property", ["embedding", "embedding_", "embedding_X", "embedding_x`) DETACH", "vec_x"])
def test_a_bad_vector_property_is_a_problem(property: str) -> None:
    assert index_problems("vec_x", Label.FRAGMENTOS, 3, property) != []
