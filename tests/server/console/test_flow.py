"""A template's flow diagram and its changes (feature 039): pure functions over the stages as the API gives them."""

import pytest

from server.console.bodies import JsonObject
from server.console.flow import find, ids, insert_after, layout, mini, move, remove, replace_stage


def stages() -> list[JsonObject]:
    return [
        {"id": "a", "action": "ingesta.select"},
        {
            "id": "c",
            "action": "cycle",
            "actor": "lab",
            "max_iterations": 3,
            "stages": [{"id": "c1", "action": "chunking.convert"}, {"id": "c2", "action": "review.score"}],
        },
        {"id": "z", "action": "external", "actor": "embeber"},
    ]


def test_every_stage_has_its_box_in_the_order_of_the_flow() -> None:
    diagram = layout(stages(), 60)
    assert [box.id for box in diagram.boxes] == ["a", "c", "c1", "c2", "z"]
    assert "( inicio )" in diagram.lines[0] and "( fin )" in diagram.lines[-1]
    assert all(len(line) <= 60 for line in diagram.lines)


def test_a_cycle_shows_who_approves_and_the_way_back() -> None:
    text = "\n".join(layout(stages(), 60).lines)
    assert "↻ c · aprueba lab · máx. 3" in text and "┌▶" in text and "otra iteración" in text
    assert "z · external · espera a embeber" in text


def test_a_click_finds_the_stage_under_it() -> None:
    diagram = layout(stages(), 60)
    box = diagram.box("c2")
    assert box is not None and diagram.at(box.x + 1, box.y + 1) == "c2" and diagram.at(0, 0) is None


def test_a_narrow_terminal_keeps_the_frame_closed() -> None:
    lines = layout(stages(), 10).lines
    framed = [line for line in lines if line.startswith(("│", "╭", "╰"))]
    assert len({len(line) for line in framed}) == 1


def test_moving_goes_past_a_neighbour_and_changes_nothing_given() -> None:
    given: list[JsonObject] = [{"id": "a", "action": "x"}, {"id": "b", "action": "x"}]
    assert ids(move(given, "a", down=True)) == ["b", "a"] and ids(given) == ["a", "b"]
    assert ids(move(given, "a", down=False)) == ["a", "b"]  # already first


def test_moving_enters_a_cycle_and_leaves_it() -> None:
    entered = move(stages(), "a", down=True)
    assert ids(entered) == ["c", "a", "c1", "c2", "z"]
    left = move(entered, "a", down=False)
    assert ids(left) == ["a", "c", "c1", "c2", "z"]
    assert ids(move(stages(), "c1", down=True)) == ["a", "c", "c2", "c1", "z"]


def test_a_cycle_goes_past_a_stage_and_never_inside_another_cycle() -> None:
    assert ids(move(stages(), "c", down=True)) == ["a", "z", "c", "c1", "c2"]
    two: list[JsonObject] = [{"id": "p", "action": "cycle", "stages": []}, *stages()[1:2]]
    assert ids(move(two, "p", down=True)) == ["c", "c1", "c2", "p"]


@pytest.mark.parametrize(("target", "expected"), [("c1", ["a", "c", "c2", "z"]), ("c", ["a", "z"])])
def test_removing_leaves_the_rest_of_its_list(target: str, expected: list[str]) -> None:
    assert ids(remove(stages(), target)) == expected


def test_a_stage_is_inserted_after_the_one_given_inside_its_cycle() -> None:
    new: JsonObject = {"id": "n", "action": "x"}
    assert ids(insert_after(stages(), "c1", new)) == ["a", "c", "c1", "n", "c2", "z"]


def test_without_a_stage_given_it_is_inserted_at_the_end() -> None:
    assert ids(insert_after(stages(), None, {"id": "n", "action": "x"}))[-1] == "n"


def test_a_cycle_is_never_inserted_inside_another_cycle() -> None:
    cycle: JsonObject = {"id": "n", "action": "cycle", "stages": []}
    assert ids(insert_after(stages(), "c1", cycle)) == ["a", "c", "c1", "c2", "n", "z"]


def test_replacing_a_step_leaves_it_in_its_cycle() -> None:
    changed = replace_stage(stages(), "c1", {"id": "c9", "action": "chunking.convert"})
    assert ids(changed) == ["a", "c", "c9", "c2", "z"] and find(changed, "c1") is None


def test_the_mini_flow_marks_the_cycles() -> None:
    assert mini(stages()) == "a → ↻c → z"
