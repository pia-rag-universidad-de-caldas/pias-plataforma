"""The console's screens: the only file that uses asciimatics. It has no types, so it is loaded with import_module and
is Any from here on (like Docling in chunking/adapters/).

Each screen is a dialog that returns a value (None with Esc): the navigation is a plain loop in app.py. The dialogs
run their own frame loop instead of Screen.play so that one of them (a run's progress) can refresh itself between
frames without threads. Texts are in Spanish (feature 035); colours use asciimatics' ${fg,attr} markup.
"""

import json
import re
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Literal, Self

type Widget = Any  # an asciimatics object (screen, frame, widget, event): the library is untyped
type Keys = Callable[[Widget], None]

_widgets = import_module("asciimatics.widgets")
_scene = import_module("asciimatics.scene")
_screen = import_module("asciimatics.screen")
_events = import_module("asciimatics.event")
_exceptions = import_module("asciimatics.exceptions")
_parsers = import_module("asciimatics.parsers")

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)
BOLD, NORMAL = 1, 2
ENTER = (10, 13)
FRAME_TIME = 0.05
HELP_HEIGHT = 7
EMPTY = "(vacío)"

# Dark theme with accents (feature 035): cyan borders, titles and selection.
PALETTE: dict[str, tuple[int, int, int]] = {
    "background": (WHITE, NORMAL, BLACK),
    "shadow": (BLACK, NORMAL, BLACK),
    "disabled": (WHITE, NORMAL, BLACK),
    "invalid": (RED, BOLD, BLACK),
    "label": (CYAN, BOLD, BLACK),
    "borders": (CYAN, NORMAL, BLACK),
    "scroll": (CYAN, NORMAL, BLACK),
    "title": (BLACK, BOLD, CYAN),
    "edit_text": (WHITE, NORMAL, BLACK),
    "focus_edit_text": (BLACK, NORMAL, CYAN),
    "readonly": (WHITE, NORMAL, BLACK),
    "focus_readonly": (WHITE, NORMAL, BLACK),
    "button": (WHITE, NORMAL, BLACK),
    "focus_button": (BLACK, BOLD, CYAN),
    "control": (YELLOW, NORMAL, BLACK),
    "selected_control": (YELLOW, BOLD, BLACK),
    "focus_control": (BLACK, NORMAL, CYAN),
    "selected_focus_control": (BLACK, BOLD, CYAN),
    "field": (WHITE, NORMAL, BLACK),
    "selected_field": (CYAN, BOLD, BLACK),
    "focus_field": (WHITE, NORMAL, BLACK),
    "selected_focus_field": (BLACK, BOLD, CYAN),
}
METHOD_COLOURS = {"GET": GREEN, "POST": YELLOW, "PUT": YELLOW, "PATCH": YELLOW, "DELETE": RED}
_JSON_TOKEN = re.compile(
    r'(?P<key>"(?:\\.|[^"\\])*")(?=\s*:)|(?P<text>"(?:\\.|[^"\\])*")|(?P<number>-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'
    r"|(?P<literal>\b(?:true|false|null)\b)"
)
_JSON_COLOURS = {"key": CYAN, "text": GREEN, "number": YELLOW, "literal": MAGENTA}


def plain(text: str) -> str:
    """Text shown as it is (asciimatics markup starts with ${)."""
    return text.replace("${", "$ {")


def paint(text: str, colour: int, bold: bool = False) -> str:
    return f"${{{colour},{BOLD if bold else NORMAL}}}{plain(text)}${{{WHITE},{NORMAL}}}"


def method(verb: str) -> str:
    return paint(f"{verb:<6}", METHOD_COLOURS.get(verb, WHITE), bold=True)


def dot(ok: bool) -> str:
    return paint("●", GREEN if ok else RED)


def json_markup(text: str) -> str:
    """Indented JSON with keys, texts, numbers and literals in colour."""

    def coloured(match: re.Match[str]) -> str:
        kind = match.lastgroup or "text"
        return f"${{{_JSON_COLOURS[kind]},{NORMAL}}}{plain(match.group())}${{{WHITE},{NORMAL}}}"

    return _JSON_TOKEN.sub(coloured, text)


def pretty(text: str) -> str:
    """An answer's text with colours when it is JSON."""
    try:
        json.loads(text)
    except ValueError:
        return plain(text)
    return json_markup(text)


@dataclass(frozen=True)
class MenuItem:
    label: str  # with markup
    help: str = ""


@dataclass(frozen=True)
class FormField:
    name: str
    label: str
    value: str
    kind: Literal["text", "check", "choice", "suggest", "object"] = "text"
    choices: tuple[str, ...] = ()
    optional: bool = True  # a drop-down with an empty first option


@dataclass(frozen=True)
class FormActions:
    optional_count: int  # optional fields the action has (in use or not)
    json: bool  # it has a body that can be edited as JSON


@dataclass(frozen=True)
class FormEvent:
    kind: Literal["send", "back", "pick", "json", "add", "remove"]
    values: Mapping[str, str] = field(default_factory=dict)
    field: str = ""  # the one whose list was asked for


@dataclass(frozen=True)
class TableEvent:
    kind: Literal["row", "previous", "next", "json", "back"]
    row: int = -1


class _Answer:
    """What the dialog answered; set right before raising StopApplication."""

    def __init__(self) -> None:
        self.value: object = None

    def give(self, value: object) -> None:
        self.value = value
        raise _exceptions.StopApplication("answered")


class _Refresh:
    """The state of a self-refreshing screen between frames."""

    def __init__(self) -> None:
        self.box: Widget = None
        self.next = 0.0
        self.done = False


def _at_top(box: Widget) -> None:
    """A TextBox that keeps showing its first lines when its text changes (asciimatics scrolls to the end)."""
    box._auto_scroll = False


def _show_from_top(listing: Widget) -> None:
    """Scrolls a list to its first line while keeping its selection visible. Its value set before the frame had a
    height (as when coming back to a menu) leaves the selection at the top and hides the lines above it."""
    listing._start_line = 0
    listing.value = listing.value


def _is_key(event: Widget, *codes: int) -> bool:
    return isinstance(event, _events.KeyboardEvent) and event.key_code in codes


class Screens:
    def __init__(self, screen: Widget) -> None:
        self._screen = screen
        self.trail: list[str] = []  # where the user is, shown as a breadcrumb on top of every screen
        self._after: list[Callable[[], None]] = []  # run once the scene started (it resets focus and lists)

    @classmethod
    @contextmanager
    def opened(cls) -> Iterator[Self]:
        """The whole terminal for the console; restored when leaving (also on an error or Ctrl+C)."""
        screens = cls(_screen.Screen.open())
        try:
            yield screens
        finally:
            screens._screen.close()

    @property
    def width(self) -> int:
        return int(self._screen.width)

    def _frame(self, title: str, scroll: bool = False) -> Widget:
        frame = _widgets.Frame(
            self._screen, self._screen.height, self._screen.width, title=f" {title} ", can_scroll=scroll
        )
        frame.palette = PALETTE
        crumbs = _widgets.Layout([1])
        frame.add_layout(crumbs)
        crumbs.add_widget(_widgets.Label(" ▸ ".join(["inicio", *self.trail])))
        crumbs.add_widget(_widgets.Divider())
        return frame

    def _play(
        self, build: Callable[[_Answer], tuple[Widget, Keys | None]], tick: Callable[[], None] | None = None
    ) -> object:
        """Shows the frame `build` makes until it answers (Esc: None, unless its keys swallow it). `tick` runs between
        frames. A resized terminal reopens the screen and rebuilds the frame."""
        answer = _Answer()
        while True:
            frame, keys = build(answer)
            frame.fix()

            def unhandled(event: Widget, keys: Keys | None = keys) -> None:
                if keys is not None:
                    keys(event)
                if _is_key(event, _screen.Screen.KEY_ESCAPE):
                    answer.give(None)

            self._screen.set_scenes([_scene.Scene([frame], -1)], unhandled_input=unhandled)
            for after in self._after:  # starting the scene resets the focus to the first widget
                after()
            self._after = []
            try:
                while True:
                    if tick is not None:
                        tick()
                    self._screen.draw_next_frame()
                    if self._screen.has_resized():
                        raise _exceptions.ResizeScreenError("resized")
                    self._screen.wait_for_input(FRAME_TIME)
            except _exceptions.StopApplication:
                return answer.value
            except _exceptions.ResizeScreenError:
                self._screen.close()
                self._screen = _screen.Screen.open()

    def _help(self, text: str, height: int) -> Widget:
        """Text that never takes the focus, wrapped and shown from its first line (the rest is cut)."""
        width = max(self.width - 4, 20)
        needed = sum(max(1, -(-len(line) // width)) for line in text.split("\n"))
        return _widgets.Label(text, height=max(1, min(needed, height)))

    def menu(
        self,
        title: str,
        intro: str,
        items: Sequence[MenuItem],
        selected: int = 0,
        escape: bool = True,
        intro_lines: int = 4,
    ) -> int | None:
        """The index of the item chosen (its help shown while highlighted), or None (Esc, unless `escape` is off)."""

        def build(answer: _Answer) -> tuple[Widget, Keys | None]:
            frame = self._frame(title)
            top = _widgets.Layout([1], fill_frame=True)
            frame.add_layout(top)
            if intro:
                top.add_widget(self._help(intro, intro_lines))
                top.add_widget(_widgets.Divider())
            help_box = _widgets.Label("", height=HELP_HEIGHT)

            def changed() -> None:
                help_box.text = items[listing.value].help if listing.value is not None else ""

            listing: Widget = _widgets.ListBox(
                _widgets.Widget.FILL_FRAME,
                [(item.label, index) for index, item in enumerate(items)],
                parser=_parsers.AsciimaticsParser(),
                on_change=changed,
                on_select=lambda: answer.give(listing.value),
            )
            top.add_widget(listing)
            bottom = _widgets.Layout([1])
            frame.add_layout(bottom)
            bottom.add_widget(_widgets.Divider())
            bottom.add_widget(help_box)
            keys_help = "↑↓ moverse · Enter elegir · " + ("Esc volver" if escape else "«salir» para terminar")
            bottom.add_widget(_widgets.Label(keys_help, align="^"))
            listing.value = min(selected, max(len(items) - 1, 0))
            changed()
            self._after.append(lambda: _show_from_top(listing))

            def keys(event: Widget) -> None:
                if not escape and _is_key(event, _screen.Screen.KEY_ESCAPE):
                    event.key_code = 0  # swallowed: Esc doesn't leave this menu

            return frame, keys

        chosen = self._play(build)
        return chosen if isinstance(chosen, int) else None

    def form(
        self,
        title: str,
        intro: str,
        fields: Sequence[FormField],
        optional: Sequence[FormField],
        actions: FormActions,
        focus: str = "",
        problem: str = "",
        heading: str = "Obligatorios",
    ) -> FormEvent:
        """The form: the required fields, then the optional ones in use. Enter on a ▾ or ✎ field asks for its list or
        its editor (`pick`); «+ Opcional» / «- Opcional» ask to add or remove optional fields."""
        every = list(fields) + list(optional)
        keys_of = {f"field_{index}": item for index, item in enumerate(every)}

        def build(answer: _Answer) -> tuple[Widget, Keys | None]:
            intro_height = self._screen.height // 3
            fits = len(every) + intro_height + 12 <= self._screen.height
            frame = self._frame(title, scroll=not fits)
            head = _widgets.Layout([1])
            frame.add_layout(head)
            head.add_widget(self._help(intro, intro_height))
            inputs = _widgets.Layout([1], fill_frame=fits)
            frame.add_layout(inputs)
            position: dict[str, int] = {}
            names = iter(keys_of)

            def add(item: FormField) -> None:
                key = next(names)
                if item.kind == "check":
                    widget = _widgets.CheckBox("", label=item.label, name=key)
                    widget.value = item.value == "true"
                elif item.kind == "choice":
                    options = [(EMPTY, "")] if item.optional else []
                    options += [(choice, choice) for choice in item.choices]
                    widget = _widgets.DropdownList(options, label=item.label, name=key)
                    widget.value = item.value if item.value in item.choices else options[0][1]
                else:
                    widget = _widgets.Text(label=item.label, name=key)
                    widget.value = item.value
                position[item.name] = len(position)
                inputs.add_widget(widget)

            inputs.add_widget(_widgets.Divider())
            inputs.add_widget(_widgets.Label(heading if fields else "Esta acción no tiene datos obligatorios."))
            for item in fields:
                add(item)
            if actions.optional_count:
                inputs.add_widget(_widgets.Divider())
                in_use = f"{len(optional)} en uso de {actions.optional_count}"
                inputs.add_widget(_widgets.Label(f"Opcionales ({in_use}; los que no están aquí no se envían)"))
                for item in optional:
                    add(item)
            message = _widgets.Label(f"✗ {problem}" if problem else "", height=2)

            def values() -> dict[str, str]:
                frame.save()
                data: Mapping[str, object] = frame.data
                found: dict[str, str] = {}
                for key, item in keys_of.items():
                    value = data.get(key)
                    found[item.name] = ("true" if value else "false") if item.kind == "check" else str(value or "")
                return found

            foot = _widgets.Layout([1])
            frame.add_layout(foot)
            foot.add_widget(_widgets.Divider())
            foot.add_widget(message)
            buttons = _widgets.Layout([1, 1, 1, 1, 1])
            frame.add_layout(buttons)
            buttons.add_widget(_widgets.Button("Enviar", lambda: answer.give(FormEvent("send", values()))), 0)
            if len(optional) < actions.optional_count:
                buttons.add_widget(_widgets.Button("+ Opcional", lambda: answer.give(FormEvent("add", values()))), 1)
            if optional:
                buttons.add_widget(_widgets.Button("- Opcional", lambda: answer.give(FormEvent("remove", values()))), 2)
            if actions.json:
                buttons.add_widget(_widgets.Button("Editar JSON", lambda: answer.give(FormEvent("json", values()))), 3)
            buttons.add_widget(_widgets.Button("Volver", lambda: answer.give(FormEvent("back"))), 4)
            foot.add_widget(_widgets.Label("Tab/↑↓ campos · Enter en ▾: lista · Enter en ✎: editor · Esc volver"))
            if focus in position:
                index = [item.name for item in every].index(focus)
                widget_index = index + 1 + (2 if index >= len(fields) and actions.optional_count else 0)
                self._after.append(lambda: frame.switch_focus(inputs, 0, widget_index + 1))

            def keys(event: Widget) -> None:
                if _is_key(event, *ENTER):
                    focussed = frame.focussed_widget
                    item = keys_of.get(getattr(focussed, "name", "") or "")
                    if item is not None and item.kind in ("suggest", "object"):
                        answer.give(FormEvent("pick", values(), item.name))

            return frame, keys

        result = self._play(build)
        return result if isinstance(result, FormEvent) else FormEvent("back")

    def checklist(
        self, title: str, intro: str, options: Sequence[tuple[str, str]], chosen: Sequence[str], single: bool
    ) -> list[str] | None:
        """The values marked (Enter marks or unmarks; with `single`, only one at a time), or None to leave them as
        they were. Typing filters the list; «Usar lo escrito» adds the text itself."""
        marked = list(chosen)

        def matching(text: str) -> list[tuple[str, str]]:
            needle = text.strip().lower()
            if not needle:
                return list(options)
            return [(v, d) for v, d in options if needle in v.lower() or needle in d.lower()]

        def build(answer: _Answer) -> tuple[Widget, Keys | None]:
            frame = self._frame(title)
            top = _widgets.Layout([1])
            frame.add_layout(top)
            top.add_widget(self._help(intro, 4))
            count = _widgets.Label("")
            widest = min(max([len(v) for v, _ in options] + [8]), 60)

            def rows(text: str) -> list[tuple[str, int]]:
                shown = matching(text)
                count.text = (
                    f"{len(shown)} de {len(options)} · marcados: {', '.join(marked) or 'ninguno'}"
                    if options
                    else "No hay valores para sugerir: escribe uno y «Usar lo escrito»."
                )
                return [
                    (f"{paint('[✓]', GREEN, bold=True) if v in marked else '[ ]'} {plain(v):<{widest}}  "
                     f"{paint(d, CYAN) if d else ''}", i)
                    for i, (v, d) in enumerate(shown)
                ]  # fmt: skip

            def toggle() -> None:
                shown = matching(search.value)
                if listing.value is None or listing.value >= len(shown):
                    return
                value = shown[listing.value][0]
                if value in marked:
                    marked.remove(value)
                else:
                    if single:
                        marked.clear()
                    marked.append(value)
                if single:
                    answer.give(list(marked))
                line = listing.value
                listing.options = rows(search.value)
                listing.value = line

            listing: Widget = _widgets.ListBox(
                _widgets.Widget.FILL_FRAME, rows(""), parser=_parsers.AsciimaticsParser(), on_select=toggle
            )

            def refilter() -> None:
                listing.options = rows(search.value)
                listing.value = 0 if listing.options else None

            def typed() -> None:
                text = search.value.strip()
                if text and text not in marked:
                    if single:
                        marked.clear()
                    marked.append(text)
                answer.give(list(marked))

            search: Widget = _widgets.Text(label="buscar", name="search", on_change=refilter)
            top.add_widget(search)
            top.add_widget(count)
            top.add_widget(_widgets.Divider())
            middle = _widgets.Layout([1], fill_frame=True)
            frame.add_layout(middle)
            middle.add_widget(listing)
            bottom = _widgets.Layout([1, 1, 1, 1])
            frame.add_layout(bottom)
            bottom.add_widget(_widgets.Button("Aceptar", lambda: answer.give(list(marked))), 0)
            bottom.add_widget(_widgets.Button("Usar lo escrito", typed), 1)
            bottom.add_widget(_widgets.Button("Limpiar", lambda: answer.give([])), 2)
            bottom.add_widget(_widgets.Button("Volver", lambda: answer.give(None)), 3)
            hint = "Enter elige" if single else "Enter marca o desmarca · «Aceptar» al terminar"
            foot = _widgets.Layout([1])
            frame.add_layout(foot)
            foot.add_widget(_widgets.Label(f"escribe para filtrar · ↓ a la lista · {hint}", align="^"))
            self._after.append(lambda: frame.switch_focus(middle, 0, 0))

            def keys(event: Widget) -> None:
                if _is_key(event, *ENTER) and frame.focussed_widget is search:
                    frame.switch_focus(middle, 0, 0)

            return frame, keys

        result = self._play(build)
        return [str(value) for value in result] if isinstance(result, list) else None

    def editor(self, title: str, text: str, check: Callable[[str], str | None]) -> str | None:
        """The JSON as edited (checked by `check`), or None to leave it as it was."""

        def build(answer: _Answer) -> tuple[Widget, Keys | None]:
            frame = self._frame(title)
            main = _widgets.Layout([1], fill_frame=True)
            frame.add_layout(main)
            box = _widgets.TextBox(_widgets.Widget.FILL_FRAME, as_string=True, name="body")
            _at_top(box)
            box.value = text
            main.add_widget(box)
            message = _widgets.Label("", height=2)
            foot = _widgets.Layout([1])
            frame.add_layout(foot)
            foot.add_widget(_widgets.Divider())
            foot.add_widget(message)

            def save() -> None:
                problem = check(box.value)
                if problem:
                    message.text = f"✗ {problem}"
                else:
                    answer.give(box.value)

            buttons = _widgets.Layout([1, 1, 3])
            frame.add_layout(buttons)
            buttons.add_widget(_widgets.Button("Guardar", save), 0)
            buttons.add_widget(_widgets.Button("Volver", lambda: answer.give(None)), 1)
            buttons.add_widget(_widgets.Label("Tab a los botones · Esc descarta", align=">"), 2)
            return frame, None

        edited = self._play(build)
        return edited if isinstance(edited, str) else None

    def table(
        self, title: str, intro: str, columns: Sequence[tuple[str, int]], rows: Sequence[Sequence[str]], paged: bool
    ) -> TableEvent:
        """A list as a table: Enter on a row, ← → between pages, or the JSON."""

        def build(answer: _Answer) -> tuple[Widget, Keys | None]:
            frame = self._frame(title)
            top = _widgets.Layout([1], fill_frame=True)
            frame.add_layout(top)
            top.add_widget(self._help(intro, 2))
            listing: Widget = _widgets.MultiColumnListBox(
                _widgets.Widget.FILL_FRAME,
                [width for _, width in columns],
                [([plain(cell) for cell in row], index) for index, row in enumerate(rows)],
                titles=[name for name, _ in columns],
                on_select=lambda: answer.give(TableEvent("row", listing.value)),
            )
            top.add_widget(listing)
            buttons = _widgets.Layout([1, 1, 1, 1, 3])
            frame.add_layout(buttons)
            if paged:
                buttons.add_widget(_widgets.Button("← Anterior", lambda: answer.give(TableEvent("previous"))), 0)
                buttons.add_widget(_widgets.Button("Siguiente →", lambda: answer.give(TableEvent("next"))), 1)
            buttons.add_widget(_widgets.Button("Ver JSON", lambda: answer.give(TableEvent("json"))), 2)
            buttons.add_widget(_widgets.Button("Volver", lambda: answer.give(TableEvent("back"))), 3)
            hint = "Enter: acciones de la fila" + (" · ← → página" if paged else "") + " · Esc volver"
            buttons.add_widget(_widgets.Label(hint, align=">"), 4)

            def keys(event: Widget) -> None:
                if paged and _is_key(event, _screen.Screen.KEY_LEFT):
                    answer.give(TableEvent("previous"))
                if paged and _is_key(event, _screen.Screen.KEY_RIGHT):
                    answer.give(TableEvent("next"))

            return frame, keys

        result = self._play(build)
        return result if isinstance(result, TableEvent) else TableEvent("back")

    def show(self, title: str, markup: str, actions: Sequence[str] = ("Volver",)) -> int | None:
        """A scrollable text (with colour markup) and a button per action: the index of the one pressed, or None."""

        def build(answer: _Answer) -> tuple[Widget, Keys | None]:
            frame = self._frame(title)
            main = _widgets.Layout([1], fill_frame=True)
            frame.add_layout(main)
            box = _widgets.TextBox(
                _widgets.Widget.FILL_FRAME,
                as_string=True,
                line_wrap=True,
                readonly=True,
                parser=_parsers.AsciimaticsParser(),
            )
            _at_top(box)
            box.value = markup
            main.add_widget(box)
            buttons = _widgets.Layout([1] * len(actions) + [2])
            frame.add_layout(buttons)
            for index, action in enumerate(actions):
                buttons.add_widget(_widgets.Button(action, lambda chosen=index: answer.give(chosen)), index)
            hint = "↑↓ desplazarse · Tab a los botones · Esc volver"
            buttons.add_widget(_widgets.Label(hint, align=">"), len(actions))
            return frame, None

        pressed = self._play(build)
        return pressed if isinstance(pressed, int) else None

    def confirm(self, title: str, text: str) -> bool:
        return self.show(title, text, ("Enviar", "Cancelar")) == 0

    def follow(self, title: str, read: Callable[[], tuple[str, bool]], every: float) -> None:
        """A text that `read` refreshes every `every` seconds until it says it is done; Esc or «Volver» leave."""
        state = _Refresh()

        def build(answer: _Answer) -> tuple[Widget, Keys | None]:
            frame = self._frame(title)
            main = _widgets.Layout([1], fill_frame=True)
            frame.add_layout(main)
            state.box = _widgets.TextBox(
                _widgets.Widget.FILL_FRAME,
                as_string=True,
                line_wrap=True,
                readonly=True,
                parser=_parsers.AsciimaticsParser(),
            )
            _at_top(state.box)
            main.add_widget(state.box)
            buttons = _widgets.Layout([1, 3])
            frame.add_layout(buttons)
            buttons.add_widget(_widgets.Button("Volver", lambda: answer.give(None)), 0)
            buttons.add_widget(_widgets.Label("se actualiza sola · Esc volver (la corrida sigue)", align=">"), 1)
            state.next, state.done = 0.0, False
            return frame, None

        def tick() -> None:
            if state.done or time.monotonic() < state.next:
                return
            text, state.done = read()
            state.box.value = text
            state.next = time.monotonic() + every

        self._play(build, tick)
