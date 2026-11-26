"""The widgets the console draws by itself: the cards (feature 037, their geometry in cards.py) and the flow diagram of
a template (feature 039, drawn from flow.py)."""

from collections.abc import Callable, Sequence

from . import toolkit
from .cards import Direction, Grid, fit, grid, hotkeys, step, wrap
from .flow import Diagram
from .screen_types import Card
from .theme import (
    BLACK,
    BLUE,
    BOLD,
    CARD_HEIGHT,
    CARD_WIDTH,
    CYAN,
    ENTER,
    GREEN,
    METHOD_COLOURS,
    NORMAL,
    RED,
    SPACE,
    WHITE,
    YELLOW,
)
from .toolkit import Widget


def at_top(box: Widget) -> None:
    """A TextBox that keeps showing its first lines when its text changes (asciimatics scrolls to the end)."""
    box._auto_scroll = False


def rounded(frame: Widget) -> None:
    """The rounded corners of the cards, on the border of a frame."""
    box = frame._border_mgr.box
    box.down_right, box.down_left, box.up_right, box.up_left = "╭", "╮", "╰", "╯"


def _cards_init(
    self: Widget,
    cards: Sequence[Card],
    on_select: Callable[[int], None],
    on_mark: Callable[[int], None] | None = None,
    on_change: Callable[[int], None] | None = None,
    height: int = CARD_HEIGHT,
    min_width: int = CARD_WIDTH,
    keys: bool = True,
    reserved: str = "",
) -> None:
    """`on_select`: Enter. `on_mark`: Space, its key or a click; without it, those select too."""
    toolkit.widgets.Widget.__init__(self, None)
    self.card_height, self.min_width = height, min_width
    self.on_select, self.on_mark, self.on_change = on_select, on_mark, on_change
    self.use_keys, self.reserved = keys, reserved
    self.index = 0
    self.set_cards(cards)


def _set_cards(self: Widget, cards: Sequence[Card]) -> None:
    self.cards = list(cards)
    self.labels = hotkeys(len(self.cards), self.reserved) if self.use_keys else [""] * len(self.cards)
    self.by_key = {ord(key): index for index, key in enumerate(self.labels) if key}
    self.index = max(0, min(self.index, len(self.cards) - 1))


def _cards_grid(self: Widget) -> Grid:
    return grid(self._w, self._h, len(self.cards), self.index, self.card_height, self.min_width)


def _cards_move(self: Widget, index: int) -> None:
    if index != self.index and 0 <= index < len(self.cards):
        self.index = index
        if self.on_change is not None:
            self.on_change(index)


def _cards_act(self: Widget, mark: bool = True) -> None:
    if self.cards and not self.cards[self.index].blocked:
        (self.on_mark if mark and self.on_mark is not None else self.on_select)(self.index)


def _cards_event(self: Widget, event: Widget) -> Widget:
    if isinstance(event, toolkit.events.MouseEvent):
        found = _cards_grid(self).at(event.x - self._x, event.y - self._y)
        if found is None:
            return event
        _cards_move(self, found)
        if event.buttons != 0:
            _cards_act(self)
        return None
    if not isinstance(event, toolkit.events.KeyboardEvent):
        return event
    code = event.key_code
    keys = toolkit.screen.Screen
    arrows: dict[int, Direction] = {keys.KEY_LEFT: "left", keys.KEY_RIGHT: "right", keys.KEY_UP: "up",
                                    keys.KEY_DOWN: "down"}  # fmt: skip
    layout = _cards_grid(self)
    per_page = layout.columns * layout.rows
    if code in arrows:
        _cards_move(self, step(self.index, arrows[code], layout.columns, len(self.cards)))
    elif code == keys.KEY_PAGE_DOWN:
        _cards_move(self, min(self.index + per_page, len(self.cards) - 1))
    elif code == keys.KEY_PAGE_UP:
        _cards_move(self, max(self.index - per_page, 0))
    elif code in ENTER:
        _cards_act(self, mark=False)
    elif code == SPACE:
        _cards_act(self)
    elif code in self.by_key:
        _cards_move(self, self.by_key[code])
        _cards_act(self)
    else:
        return event
    return None


def _draw_card(canvas: Widget, card: Card, key: str, x: int, y: int, width: int, height: int, focus: bool) -> None:
    """A rounded card: blue, or cyan when highlighted; its key, mark, state, method and title on the first line."""
    background = CYAN if focus else BLACK if card.blocked else BLUE
    ink = BLACK if focus else WHITE
    canvas.print_at("╭" + "─" * (width - 2) + "╮", x, y, ink, NORMAL, background)
    for line in range(1, height - 1):
        canvas.print_at("│" + " " * (width - 2) + "│", x, y + line, ink, NORMAL, background)
    canvas.print_at("╰" + "─" * (width - 2) + "╯", x, y + height - 1, ink, NORMAL, background)
    inner = width - 4
    cursor = x + 2

    def part(text: str, colour: int, attr: int = BOLD) -> None:
        nonlocal cursor
        canvas.print_at(text, cursor, y + 1, ink if focus else colour, NORMAL if focus else attr, background)
        cursor += len(text)

    if card.blocked:
        part("⊘ ", RED)
    elif key:
        part(f"[{key}] ", YELLOW)
    if card.marked is not None:
        part("✓ " if card.marked else "· ", GREEN)
    if card.status is not None:
        part("● " if card.status else "✗ ", GREEN if card.status else RED)
    if card.verb:
        part(f"{card.verb:<7}", METHOD_COLOURS.get(card.verb, WHITE))
    part(fit(card.title, max(x + 2 + inner - cursor, 0)), WHITE)
    colour = ink if focus or not card.alert else YELLOW
    text = f"Bloqueado: {card.blocked}" if card.blocked else card.text
    colour = RED if card.blocked and not focus else colour
    for index, line_text in enumerate(wrap(text, inner, height - 3)):
        canvas.print_at(line_text, x + 2, y + 2 + index, colour, NORMAL, background)


def _cards_update(self: Widget, _: int) -> None:
    layout = _cards_grid(self)
    canvas = self._frame.canvas
    if not self.cards and self.empty:
        canvas.print_at(self.empty, self._x + max(0, (self._w - len(self.empty)) // 2), self._y + self._h // 2, CYAN)
    for index in layout.shown:
        left, top = layout.place(index)
        _draw_card(
            canvas,
            self.cards[index],
            self.labels[index],
            self._x + left,
            self._y + top,
            layout.card_width,
            layout.card_height,
            self._has_focus and index == self.index,
        )
    if layout.pages > 1:
        note = f"página {layout.page + 1} de {layout.pages} · ↑↓ o AvPág para ver más"
        canvas.print_at(note, self._x + max(0, (self._w - len(note)) // 2), self._y + self._h - 1, CYAN, NORMAL, BLACK)


# Built with type() so that it isn't a class statement subclassing an untyped (Any) base.
Cards = type(
    "Cards",
    (toolkit.widgets.Widget,),
    {
        "__init__": _cards_init,
        "empty": "",
        "set_cards": _set_cards,
        "process_event": _cards_event,
        "update": _cards_update,
        "reset": lambda self: None,
        "required_height": lambda self, offset, width: toolkit.widgets.Widget.FILL_FRAME,
        "value": property(lambda self: self.index, lambda self, index: setattr(self, "index", index)),
    },
)


def _flow_init(self: Widget, diagram: Diagram, selected: str | None, on_select: Callable[[], None]) -> None:
    toolkit.widgets.Widget.__init__(self, None)
    self.diagram, self.on_select, self.on_change = diagram, on_select, None
    self.selected = selected if diagram.box(selected or "") else (diagram.boxes[0].id if diagram.boxes else None)


def _flow_left(self: Widget) -> int:
    width = max((len(line) for line in self.diagram.lines), default=0)
    return int(self._x) + max((int(self._w) - width) // 2, 0)


def _flow_top(self: Widget) -> int:
    """The first line of the diagram shown: enough for the selected stage to be seen, with some of what surrounds it."""
    box = self.diagram.box(self.selected or "")
    height = int(self._h)
    if box is None or len(self.diagram.lines) <= height:
        return 0
    top = box.y + box.height // 2 - height // 2
    return int(max(0, min(top, len(self.diagram.lines) - height)))


def _flow_move(self: Widget, id: str) -> None:
    self.selected = id
    if self.on_change is not None:
        self.on_change(id)


def _flow_event(self: Widget, event: Widget) -> Widget:
    if isinstance(event, toolkit.events.MouseEvent):
        found = self.diagram.at(event.x - _flow_left(self), event.y - self._y + _flow_top(self))
        if found is None or not self.is_mouse_over(event):
            return event
        _flow_move(self, found)
        if event.buttons != 0:
            self.on_select()
        return None
    if not isinstance(event, toolkit.events.KeyboardEvent):
        return event
    keys = toolkit.screen.Screen
    order = [box.id for box in self.diagram.boxes]
    if event.key_code in (keys.KEY_UP, keys.KEY_DOWN) and self.selected in order:
        index = order.index(self.selected) + (1 if event.key_code == keys.KEY_DOWN else -1)
        if 0 <= index < len(order):
            _flow_move(self, order[index])
        return None
    if event.key_code in ENTER and self.selected:
        self.on_select()
        return None
    return event


def _flow_update(self: Widget, _: int) -> None:
    canvas = self._frame.canvas
    left, top = _flow_left(self), _flow_top(self)
    lines = self.diagram.lines

    def shown(row: int, column: int, text: str, ink: int, attr: int, background: int) -> None:
        if top <= row < top + self._h:
            room = max(self._w - (column + left - self._x), 0)
            canvas.print_at(text[:room], left + column, self._y + row - top, ink, attr, background)

    for row, line in enumerate(lines):
        shown(row, 0, line, CYAN, NORMAL, BLACK)
    for box in self.diagram.boxes:
        focus = box.id == self.selected
        ink = BLACK if focus else YELLOW if box.cycle else WHITE
        background = CYAN if focus else BLACK if box.cycle else BLUE
        for row in range(box.y, box.y + box.height):
            shown(row, box.x, lines[row][box.x : box.x + box.width], ink, BOLD if box.cycle else NORMAL, background)


Flow = type(
    "Flow",
    (toolkit.widgets.Widget,),
    {
        "__init__": _flow_init,
        "process_event": _flow_event,
        "update": _flow_update,
        "reset": lambda self: None,
        "required_height": lambda self, offset, width: toolkit.widgets.Widget.FILL_FRAME,
        "value": property(lambda self: self.selected, lambda self, id: setattr(self, "selected", id)),
    },
)


def is_key(event: Widget, *codes: int) -> bool:
    return isinstance(event, toolkit.events.KeyboardEvent) and event.key_code in codes
