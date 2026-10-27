"""Order.check / reorder / move (feature 028): what each stage needs must be given by one before it."""

import pytest

from pipeline.domain import PIAA, order
from pipeline.models import CYCLE, InvalidTemplate, Stage


def _ids(stages: tuple[Stage, ...]) -> list[str]:
    return [s.id for s in stages]


def test_the_builtin_template_is_valid() -> None:
    order.check(PIAA.stages)


def test_a_stage_before_what_it_needs_is_rejected_with_its_name() -> None:
    stages = order.reorder(PIAA.stages, ["conversion", "seleccionar", *_ids(PIAA.stages)[2:]])
    with pytest.raises(InvalidTemplate, match="'convertir' needs \\['lote_archivos'\\]"):
        order.check(stages)


def test_promoting_needs_the_approved_version_not_the_raw_one() -> None:
    stages = (Stage("s", "ingesta.select"), Stage("c", "chunking.convert"), Stage("p", "data.promote_conversion"))
    with pytest.raises(InvalidTemplate, match="conversion_aprobada"):
        order.check(stages)


def test_an_external_stage_can_go_inside_a_cycle_before_its_review() -> None:
    embed = Stage("embeber", "external", actor="embeber", needs=("chunks",), gives=("embeddings",))
    stages = list(PIAA.stages)
    cycle = stages[4]
    stages[4] = Stage(cycle.id, CYCLE, cycle.params, cycle.actor, (cycle.stages[0], embed, cycle.stages[1]))
    stages = [s for s in stages if s.id != "embeber"]
    order.check(tuple(stages))


def test_a_cycle_must_end_with_its_review_and_have_an_actor() -> None:
    no_review = Stage("c", CYCLE, actor="lab", stages=(Stage("x", "ingesta.select"),))
    with pytest.raises(InvalidTemplate, match=r"review\.score"):
        order.check((no_review,))
    no_actor = Stage("c", CYCLE, stages=(Stage("r", "review.score"),))
    with pytest.raises(InvalidTemplate, match="actor"):
        order.check((no_actor,))


def test_review_outside_a_cycle_unknown_actions_and_repeated_ids() -> None:
    with pytest.raises(InvalidTemplate, match="only goes inside a cycle"):
        order.check((Stage("r", "review.score"),))
    with pytest.raises(InvalidTemplate, match="unknown action"):
        order.check((Stage("x", "nope"),))
    with pytest.raises(InvalidTemplate, match="repeated"):
        order.check((Stage("x", "ingesta.select"), Stage("x", "ingesta.select")))


def test_reorder_needs_every_top_level_id_once() -> None:
    with pytest.raises(InvalidTemplate, match="each top-level"):
        order.reorder(PIAA.stages, ["seleccionar"])


def test_move_within_the_template_and_within_a_cycle() -> None:
    moved = order.move(PIAA.stages, "revisar", before="embeber")
    assert _ids(moved)[-2:] == ["revisar", "embeber"]
    with pytest.raises(InvalidTemplate, match="needs \\['embeddings'\\]"):
        order.check(moved)
    inside = order.move(PIAA.stages, "convertir", after="puntuar_conversion")
    assert _ids(inside[1].stages) == ["puntuar_conversion", "convertir"]
    with pytest.raises(InvalidTemplate, match="isn't next to"):
        order.move(PIAA.stages, "convertir", before="embeber")
    with pytest.raises(InvalidTemplate, match="exactly one"):
        order.move(PIAA.stages, "embeber")
