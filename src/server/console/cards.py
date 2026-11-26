"""The card grid without a screen (feature 037): which key opens each card, how many fit, where each one goes and which
one is under the mouse. widgets.py draws it."""

import textwrap
from dataclasses import dataclass
from typing import Literal

HOTKEYS = "123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
GAP_X = 2
GAP_Y = 1
MAX_WIDTH = 44

type Direction = Literal["left", "right", "up", "down"]


def hotkeys(count: int, reserved: str = "") -> list[str]:
    """The key of each card, in order; "" for the ones past the last key."""
    free = [key for key in HOTKEYS if key not in reserved]
    return [free[index] if index < len(free) else "" for index in range(count)]


@dataclass(frozen=True)
class Grid:
    """A page of cards inside a box: only the page of the selected card is shown."""

    count: int
    columns: int
    rows: int  # rows of cards that fit in a page
    card_width: int
    card_height: int
    left: int  # relative to the box
    top: int
    page: int  # 0-based
    pages: int

    @property
    def shown(self) -> range:
        first = self.page * self.columns * self.rows
        return range(first, min(first + self.columns * self.rows, self.count))

    def place(self, index: int) -> tuple[int, int]:
        """The top left corner of a card of this page, relative to the box."""
        offset = index - self.shown.start
        column, row = offset % self.columns, offset // self.columns
        return self.left + column * (self.card_width + GAP_X), self.top + row * (self.card_height + GAP_Y)

    def at(self, x: int, y: int) -> int | None:
        """The card of this page at a point relative to the box."""
        for index in self.shown:
            left, top = self.place(index)
            if left <= x < left + self.card_width and top <= y < top + self.card_height:
                return index
        return None


def grid(width: int, height: int, count: int, selected: int, card_height: int, min_width: int) -> Grid:
    """The grid that fits in a box. A page indicator takes the last line when there is more than one page."""
    card_height = max(3, min(card_height, height))
    columns = max(1, (width + GAP_X) // (min_width + GAP_X))
    columns = min(columns, max(count, 1))
    card_width = min(max(MAX_WIDTH, min_width), max(1, (width - GAP_X * (columns - 1)) // columns))
    if card_width < min_width:  # not even one fits as asked: one column, as wide as there is
        columns, card_width = 1, max(1, width)
    fits = max(1, (height + GAP_Y) // (card_height + GAP_Y))
    needed = max(1, -(-count // columns))
    if needed > fits:
        fits = max(1, height // (card_height + GAP_Y))  # the same, with one line less for the indicator
    rows = min(fits, needed)
    per_page = columns * fits
    pages = max(1, -(-count // per_page))
    page = min(max(selected, 0) // per_page, pages - 1)
    used_width = columns * card_width + GAP_X * (columns - 1)
    used_height = rows * card_height + GAP_Y * (rows - 1)
    return Grid(
        count=count,
        columns=columns,
        rows=fits,
        card_width=card_width,
        card_height=card_height,
        left=max(0, (width - used_width) // 2),
        top=0 if pages > 1 else max(0, (height - used_height) // 2),
        page=page,
        pages=pages,
    )


def step(index: int, direction: Direction, columns: int, count: int) -> int:
    """The card an arrow goes to; it stays at the edges, and down from a short last row goes to the last card."""
    if count == 0:
        return 0
    moved = {"left": index - 1, "right": index + 1, "up": index - columns, "down": index + columns}[direction]
    if direction in ("left", "right"):
        return moved if 0 <= moved < count else index
    if moved < 0:
        return index
    if moved >= count:
        same_row = index // columns == (count - 1) // columns
        return index if same_row else count - 1
    return moved


def fit(text: str, width: int) -> str:
    """One line of at most `width` characters, with … if it was cut."""
    line = " ".join(text.split())
    if len(line) <= width:
        return line
    return f"{line[: max(width - 1, 0)]}…" if width > 0 else ""


def wrap(text: str, width: int, lines: int) -> list[str]:
    """At most `lines` lines of at most `width` characters; … if something didn't fit."""
    if width <= 0 or lines <= 0:
        return []
    wrapped = textwrap.wrap(" ".join(text.split()), width) or []
    if len(wrapped) <= lines:
        return wrapped
    return [*wrapped[: lines - 1], fit(" ".join(wrapped[lines - 1 :]), width)]


def reflow(text: str, width: int) -> str:
    """Long text wrapped by words, each line keeping its indentation; in an indented line, what wraps goes further."""
    lines: list[str] = []
    for line in text.split("\n"):
        indent = line[: len(line) - len(line.lstrip())]
        lines += textwrap.wrap(line, max(width, 10), subsequent_indent=f"{indent}  " if indent else "") or [""]
    return "\n".join(lines)
