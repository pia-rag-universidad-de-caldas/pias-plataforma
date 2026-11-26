"""The geometry and keys of the console's cards (feature 037), without a screen."""

import pytest

from server.console.cards import Direction, fit, grid, hotkeys, reflow, step, wrap


def test_each_card_has_its_own_key_skipping_the_reserved_ones() -> None:
    assert hotkeys(3) == ["1", "2", "3"]
    keys = hotkeys(12, reserved="a?")
    assert keys[9] == "b" and "a" not in keys and len(set(keys)) == 12


def test_cards_past_the_last_key_have_none() -> None:
    keys = hotkeys(70)
    assert keys[60] != "" and keys[61] == "" and keys[-1] == ""


def test_as_many_columns_as_fit_centred_in_the_box() -> None:
    layout = grid(100, 30, 6, 0, card_height=6, min_width=30)
    assert layout.columns == 3 and layout.pages == 1
    left, _ = layout.place(0)
    right, _ = layout.place(2)
    assert left == 100 - (right + layout.card_width)  # the same margin on both sides


def test_few_cards_are_not_stretched_or_placed_in_empty_columns() -> None:
    layout = grid(200, 30, 2, 0, card_height=6, min_width=30)
    assert layout.columns == 2 and layout.card_width <= 44


def test_a_narrow_box_still_has_one_column_inside_it() -> None:
    layout = grid(20, 30, 3, 0, card_height=6, min_width=30)
    assert layout.columns == 1 and layout.card_width == 20


def test_only_the_page_of_the_selected_card_is_shown() -> None:
    layout = grid(100, 14, 12, 0, card_height=6, min_width=30)
    assert layout.pages > 1 and layout.shown.start == 0
    per_page = layout.columns * layout.rows
    last = grid(100, 14, 12, 11, card_height=6, min_width=30)
    assert last.page == layout.pages - 1 and 11 in last.shown
    assert grid(100, 14, 12, per_page, card_height=6, min_width=30).shown.start == per_page


def test_every_card_of_every_page_fits_in_the_box_with_the_page_indicator() -> None:
    height = 14
    for selected in range(40):
        layout = grid(100, height, 40, selected, card_height=6, min_width=30)
        for index in layout.shown:
            _, top = layout.place(index)
            assert top + layout.card_height <= height - 1


def test_a_point_finds_the_card_under_it_and_the_gaps_find_none() -> None:
    layout = grid(100, 30, 6, 0, card_height=6, min_width=30)
    left, top = layout.place(4)
    assert layout.at(left, top) == 4
    assert layout.at(left + layout.card_width - 1, top + layout.card_height - 1) == 4
    assert layout.at(left + layout.card_width, top) is None
    assert layout.at(left, top + layout.card_height) is None


@pytest.mark.parametrize(
    ("index", "direction", "expected"),
    [
        (0, "left", 0),  # the edges stay
        (0, "up", 0),
        (0, "right", 1),
        (1, "down", 4),
        (4, "up", 1),
        (2, "down", 4),  # down from a full row to a short last one: the last card
        (4, "down", 4),  # already on the last row
        (4, "right", 4),
    ],
)
def test_arrows_move_in_the_grid(index: int, direction: Direction, expected: int) -> None:
    assert step(index, direction, columns=3, count=5) == expected


def test_arrows_on_no_cards_do_nothing() -> None:
    assert step(0, "down", columns=3, count=0) == 0


def test_text_is_cut_with_an_ellipsis_only_when_it_does_not_fit() -> None:
    assert fit("corto", 10) == "corto"
    assert fit("bastante largo", 8) == "bastant…"
    assert wrap("uno dos tres cuatro", 8, 2) == ["uno dos", "tres cu…"]
    assert wrap("uno", 8, 2) == ["uno"]
    assert wrap("uno", 0, 2) == []


def test_a_guide_is_wrapped_by_words_keeping_its_indentation() -> None:
    assert reflow("uno dos tres\n\n  cuatro cinco seis", 10) == "uno dos\ntres\n\n  cuatro\n    cinco\n    seis"


def test_wide_cards_never_leave_one_off_the_box() -> None:
    layout = grid(116, 20, 3, 0, 6, 54)
    assert layout.columns == 2 and layout.card_width == 54
    assert all(layout.place(index)[0] + layout.card_width <= 116 for index in layout.shown)
    narrow = grid(40, 20, 3, 0, 6, 54)
    assert narrow.columns == 1 and narrow.card_width == 40
