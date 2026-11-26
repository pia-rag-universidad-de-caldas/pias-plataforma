"""The console's screens, all of them as `Screens`. Each screen is a dialog that returns a value (None with Esc): the
navigation is a plain loop in app.py. Texts are in Spanish (feature 035)."""

import time
from collections.abc import Callable, Mapping, Sequence

from . import toolkit
from .cards import fit
from .modals import Modals
from .screen_types import Answer, FormActions, FormEvent, FormField, Refresh, TableEvent
from .theme import BACK, EMPTY, ENTER, plain
from .toolkit import Keys, Widget
from .widgets import at_top, is_key


class Screens(Modals):
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
        modal: bool = False,
    ) -> FormEvent:
        """The form: the required fields, then the optional ones in use. Enter on a ▾ or ✎ field asks for its list or
        its editor (`pick`). Letters go to the fields, so the buttons answer to function keys (feature 037)."""
        every = list(fields) + list(optional)
        keys_of = {f"field_{index}": item for index, item in enumerate(every)}

        def build(answer: Answer) -> tuple[Widget, Keys | None]:
            intro_height = self._wrapped(intro, self._modal_size(0)[1]) if modal else self._screen.height // 3
            size = self._modal_size(len(every) + intro_height + 11) if modal else None
            total = size[0] if size else self._screen.height
            width = size[1] if size else self.width
            fits = len(every) + intro_height + (11 if modal else 12) <= total
            frame = self._frame(title, scroll=not fits, modal=size)
            head = toolkit.widgets.Layout([1])
            frame.add_layout(head)
            head.add_widget(self._help(intro, intro_height, width))
            inputs = toolkit.widgets.Layout([1], fill_frame=fits)
            frame.add_layout(inputs)
            position: dict[str, int] = {}
            names = iter(keys_of)
            previews: list[tuple[Widget, Callable[[str], str]]] = []

            def add(item: FormField) -> None:
                key = next(names)
                if item.kind == "object":  # a button: its content is edited apart, in a modal
                    widget = toolkit.widgets.Button(item.label, lambda: None, label=item.label, name=key)
                    content = item.value if item.value not in ("", "{}") else "vacío"
                    widget._text = f"[ Editar: {fit(content, max(width - 40, 10))} ]"
                    widget._on_click = lambda: answer.give(FormEvent("pick", values(), item.name))
                elif item.kind == "check":
                    widget = toolkit.widgets.CheckBox("", label=item.label, name=key)
                    widget.value = item.value == "true"
                elif item.kind == "choice":
                    options = [(EMPTY, "")] if item.optional else []
                    options += [(choice, choice) for choice in item.choices]
                    widget = toolkit.widgets.DropdownList(options, label=item.label, name=key)
                    widget.value = item.value if item.value in item.choices else options[0][1]
                else:
                    widget = toolkit.widgets.Text(label=item.label, name=key)
                    widget.value = item.value
                    if item.preview is not None:
                        previews.append((widget, item.preview))
                position[item.name] = len(position)
                inputs.add_widget(widget)

            inputs.add_widget(toolkit.widgets.Divider())
            inputs.add_widget(toolkit.widgets.Label(heading if fields else ""))
            for item in fields:
                add(item)
            if actions.optional_count:
                inputs.add_widget(toolkit.widgets.Divider())
                in_use = f"{len(optional)} en uso de {actions.optional_count}"
                inputs.add_widget(toolkit.widgets.Label(f"Opcionales ({in_use}; los que no están aquí no se envían)"))
                for item in optional:
                    add(item)
            message = toolkit.widgets.Label(f"✗ {problem}" if problem else "", height=2)
            for typed, says in previews:

                def said(typed: Widget = typed, says: Callable[[str], str] = says) -> None:
                    message.text = says(typed.value)

                typed._on_change = said
                if not problem:
                    said()

            def values() -> dict[str, str]:
                frame.save()
                data: Mapping[str, object] = frame.data
                found: dict[str, str] = {}
                for key, item in keys_of.items():
                    value = data.get(key)
                    if item.kind == "object":
                        found[item.name] = item.value
                    else:
                        found[item.name] = ("true" if value else "false") if item.kind == "check" else str(value or "")
                return found

            foot = toolkit.widgets.Layout([1])
            frame.add_layout(foot)
            foot.add_widget(toolkit.widgets.Divider())
            foot.add_widget(message)
            screen = toolkit.screen.Screen
            pressed: dict[int, Callable[[], None]] = {
                screen.KEY_F2: lambda: answer.give(FormEvent("send", values())),
            }
            buttons: list[tuple[str, Callable[[], None]]] = [(f"F2 {actions.send}", pressed[screen.KEY_F2])]
            if len(optional) < actions.optional_count:
                pressed[screen.KEY_F3] = lambda: answer.give(FormEvent("add", values()))
                buttons.append(("F3 + Opcional", pressed[screen.KEY_F3]))
            if optional:
                pressed[screen.KEY_F4] = lambda: answer.give(FormEvent("remove", values()))
                buttons.append(("F4 - Opcional", pressed[screen.KEY_F4]))
            if actions.json:
                pressed[screen.KEY_F5] = lambda: answer.give(FormEvent("json", values()))
                buttons.append(("F5 JSON", pressed[screen.KEY_F5]))
            if actions.guide:
                pressed[screen.KEY_F6] = lambda: answer.give(FormEvent("help", values()))
                buttons.append(("F6 Guía", pressed[screen.KEY_F6]))
            buttons.append((BACK, lambda: answer.give(FormEvent("back"))))
            self._buttons(frame, buttons)
            hint = toolkit.widgets.Layout([1])
            frame.add_layout(hint)
            hint.add_widget(toolkit.widgets.Label("Tab/↑↓ campos · Enter en ▾: lista · Enter en ✎: editar", align="^"))
            if focus in position:
                index = [item.name for item in every].index(focus)
                widget_index = index + 1 + (2 if index >= len(fields) and actions.optional_count else 0)
                self._after.append(lambda: frame.switch_focus(inputs, 0, widget_index + 1))

            def keys(event: Widget) -> None:
                if is_key(event, *ENTER):
                    focussed = frame.focussed_widget
                    item = keys_of.get(getattr(focussed, "name", "") or "")
                    if item is not None and item.kind == "suggest":
                        answer.give(FormEvent("pick", values(), item.name))
                for code, action in pressed.items():
                    if is_key(event, code):
                        action()

            return frame, keys

        result = self._play(build)
        return result if isinstance(result, FormEvent) else FormEvent("back")

    def table(
        self, title: str, intro: str, columns: Sequence[tuple[str, int]], rows: Sequence[Sequence[str]], paged: bool
    ) -> TableEvent:
        """A list as a table: Enter on a row, ← → between pages, or the JSON."""

        def build(answer: Answer) -> tuple[Widget, Keys | None]:
            frame = self._frame(title)
            top = toolkit.widgets.Layout([1], fill_frame=True)
            frame.add_layout(top)
            top.add_widget(self._help(intro, 2))
            listing: Widget = toolkit.widgets.MultiColumnListBox(
                toolkit.widgets.Widget.FILL_FRAME,
                [width for _, width in columns],
                [([plain(cell) for cell in row], index) for index, row in enumerate(rows)],
                titles=[name for name, _ in columns],
                on_select=lambda: answer.give(TableEvent("row", listing.value)),
            )
            top.add_widget(listing)
            actions: list[tuple[str, Callable[[], None]]] = []
            if paged:
                actions.append(("← Anterior", lambda: answer.give(TableEvent("previous"))))
                actions.append(("Siguiente →", lambda: answer.give(TableEvent("next"))))
            actions.append(("F5 JSON", lambda: answer.give(TableEvent("json"))))
            actions.append((BACK, lambda: answer.give(TableEvent("back"))))
            self._buttons(frame, actions)
            foot = toolkit.widgets.Layout([1])
            frame.add_layout(foot)
            hint = "Enter: acciones de la fila" + (" · ← → página" if paged else "")
            foot.add_widget(toolkit.widgets.Label(hint, align="^"))

            def keys(event: Widget) -> None:
                if is_key(event, toolkit.screen.Screen.KEY_F5):
                    answer.give(TableEvent("json"))
                if paged and is_key(event, toolkit.screen.Screen.KEY_LEFT):
                    answer.give(TableEvent("previous"))
                if paged and is_key(event, toolkit.screen.Screen.KEY_RIGHT):
                    answer.give(TableEvent("next"))

            return frame, keys

        result = self._play(build)
        return result if isinstance(result, TableEvent) else TableEvent("back")

    def follow(self, title: str, read: Callable[[], tuple[str, bool]], every: float) -> None:
        """A text that `read` refreshes every `every` seconds until it says it is done; Esc or «Volver» leave."""
        state = Refresh()

        def build(answer: Answer) -> tuple[Widget, Keys | None]:
            frame = self._frame(title)
            main = toolkit.widgets.Layout([1], fill_frame=True)
            frame.add_layout(main)
            state.box = toolkit.widgets.TextBox(
                toolkit.widgets.Widget.FILL_FRAME,
                as_string=True,
                line_wrap=True,
                readonly=True,
                parser=toolkit.parsers.AsciimaticsParser(),
            )
            at_top(state.box)
            main.add_widget(state.box)
            self._buttons(frame, [(BACK, lambda: answer.give(None))])
            foot = toolkit.widgets.Layout([1])
            frame.add_layout(foot)
            foot.add_widget(toolkit.widgets.Label("se actualiza sola · al volver la corrida sigue", align="^"))
            state.next, state.done = 0.0, False
            return frame, None

        def tick() -> None:
            if state.done or time.monotonic() < state.next:
                return
            text, state.done = read()
            state.box.value = text
            state.next = time.monotonic() + every

        self._play(build, tick)
