"""Order.check / reorder / move (features 028 and 044): what each stage needs must be given by one before it."""

import pytest

from pipeline.domain import BUILTIN, LABORATORY, PRODUCTION, order
from pipeline.models import CYCLE, InvalidTemplate, Stage, Template


def _ids(stages: tuple[Stage, ...]) -> list[str]:
    return [s.id for s in stages]


def accepted(stages: tuple[Stage, ...]) -> bool:
    """check() only says something when it rejects: with a reason, the test fails with it."""
    try:
        order.check(stages)
    except InvalidTemplate as rejected:
        pytest.fail(f"it should be valid: {rejected}")
    return True


@pytest.mark.parametrize("template", list(BUILTIN.values()), ids=list(BUILTIN))
def test_the_builtin_templates_are_valid(template: Template) -> None:
    assert accepted(template.stages)


def test_the_builtin_templates_are_production_laboratory_and_experiments() -> None:
    assert sorted(BUILTIN) == ["experimentos", "laboratorio", "produccion"]


def test_the_laboratory_applies_the_llm_after_the_embeddings() -> None:
    assert _ids(LABORATORY.stages)[-3:] == ["aplicar_chunking", "aplicar_embeddings", "aplicar_llm"]


def test_applying_the_llm_needs_an_approved_embeddings_experiment() -> None:
    stages = order.move(LABORATORY.stages, "aplicar_llm", before="laboratorio")
    with pytest.raises(InvalidTemplate, match="'aplicar_llm' needs \\['experimento_embeddings_aprobado'\\]"):
        order.check(stages)


def test_a_stage_before_what_it_needs_is_rejected_with_its_name() -> None:
    stages = order.reorder(PRODUCTION.stages, ["parsear", "ingestar", *_ids(PRODUCTION.stages)[2:]])
    with pytest.raises(InvalidTemplate, match="'parsear' needs \\['archivos_raw'\\]"):
        order.check(stages)


def test_applying_needs_the_approved_experiment_not_the_raw_one() -> None:
    stages = (
        Stage("s", "ingesta.chunkable"),
        Stage("p", "parsing.parse"),
        Stage("x", "chunking.experiment"),
        Stage("a", "chunking.apply"),
    )
    with pytest.raises(InvalidTemplate, match="experimento_chunking_aprobado"):
        order.check(stages)


def test_embedding_an_experiment_needs_a_chunking_experiment_before_it() -> None:
    at = _ids(LABORATORY.stages).index("laboratorio")
    swapped = order.move(LABORATORY.stages, "embeber", before="chunkear")
    assert _ids(swapped[at].stages) == ["embeber", "chunkear", "puntuar"]
    with pytest.raises(InvalidTemplate, match="experimento_chunking"):
        order.check(swapped)


def test_an_external_stage_can_go_inside_a_cycle_before_its_review() -> None:
    note = Stage("nota", "external", actor="lab", needs=("experimento_chunking",), gives=("nota",))
    stages = list(LABORATORY.stages)
    at = _ids(LABORATORY.stages).index("laboratorio")
    cycle = stages[at]
    stages[at] = Stage(cycle.id, CYCLE, cycle.params, cycle.actor, (*cycle.stages[:2], note, cycle.stages[2]))
    assert accepted(tuple(stages))


def test_a_cycle_must_end_with_its_review_and_have_an_actor() -> None:
    no_review = Stage("c", CYCLE, actor="lab", stages=(Stage("x", "ingesta.chunkable"),))
    with pytest.raises(InvalidTemplate, match=r"review\.score"):
        order.check((no_review,))
    no_actor = Stage("c", CYCLE, stages=(Stage("r", "review.score"),))
    with pytest.raises(InvalidTemplate, match="actor"):
        order.check((no_actor,))


@pytest.mark.parametrize(
    ("stages", "message"),
    [
        ((Stage("r", "review.score"),), "only goes inside a cycle"),
        ((Stage("x", "nope"),), "unknown action"),
        ((Stage("x", "ingesta.chunkable"), Stage("x", "ingesta.chunkable")), "repeated"),
        ((Stage("x", "chunking.convert"),), "unknown action"),  # the piaa actions are gone (feature 044)
    ],
)
def test_what_a_template_cant_have(stages: tuple[Stage, ...], message: str) -> None:
    with pytest.raises(InvalidTemplate, match=message):
        order.check(stages)


def test_reorder_needs_every_top_level_id_once() -> None:
    with pytest.raises(InvalidTemplate, match="each top-level"):
        order.reorder(PRODUCTION.stages, ["ingestar"])


def test_move_within_the_template_and_within_a_cycle() -> None:
    moved = order.move(PRODUCTION.stages, "embeber", before="chunkear")
    assert _ids(moved)[-2:] == ["embeber", "chunkear"]
    with pytest.raises(InvalidTemplate, match="needs \\['chunkeados'\\]"):
        order.check(moved)
    with pytest.raises(InvalidTemplate, match="isn't next to"):
        order.move(LABORATORY.stages, "chunkear", before="seleccionar")
    with pytest.raises(InvalidTemplate, match="exactly one"):
        order.move(PRODUCTION.stages, "embeber")
