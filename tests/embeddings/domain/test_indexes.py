"""The vector index name: what it holds, stable, and another one for another model, dimension or label."""

import re

from embeddings.config import DEFAULT_MODEL
from embeddings.domain import fingerprint_key, index_for, index_name, property_for, vector_index, vector_property
from embeddings.models import GraphLabel


def test_the_name_says_label_model_and_dimensions() -> None:
    assert vector_index(GraphLabel.FRAGMENTOS, DEFAULT_MODEL).name == (
        "vec_fragmentos_paraphrase_multilingual_minilm_l12_v2_384"
    )


def test_the_same_model_gives_the_same_name() -> None:
    assert vector_index(GraphLabel.FRAGMENTOS, DEFAULT_MODEL) == vector_index(GraphLabel.FRAGMENTOS, DEFAULT_MODEL)


def test_another_model_dimension_or_label_gives_another_name() -> None:
    base = index_name("FRAGMENTOS", DEFAULT_MODEL, 384)
    assert base != index_name("FRAGMENTOS", "other/model-x", 384)
    assert base != index_name("FRAGMENTOS", DEFAULT_MODEL, 768)
    assert base != index_name("EXP_EMBED", DEFAULT_MODEL, 384)


def test_only_lowercase_letters_digits_and_underscores_after_vec() -> None:
    assert re.fullmatch(r"vec_[a-z0-9_]+", index_name("EXP_CHUNK", "Org/Some.Model--V2", 12))


def test_the_property_and_fingerprint_carry_the_model_and_its_dimensions() -> None:
    assert vector_property(DEFAULT_MODEL) == "embedding_paraphrase_multilingual_minilm_l12_v2_384"
    assert fingerprint_key(DEFAULT_MODEL) == "huella_embedding_paraphrase_multilingual_minilm_l12_v2_384"
    assert property_for("BAAI/bge-m3", 1024) == "embedding_bge_m3_1024"


def test_an_index_is_named_after_its_label_and_property() -> None:
    index = vector_index(GraphLabel.EXP_EMBED, DEFAULT_MODEL)
    assert (index.name, index.property) == (
        "vec_exp_embed_paraphrase_multilingual_minilm_l12_v2_384",
        vector_property(DEFAULT_MODEL),
    )
    assert index_for("FRAGMENTOS", "embedding_bge_m3_1024") == "vec_fragmentos_bge_m3_1024"
