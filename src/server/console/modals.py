"""What opens over another screen, or shows a text: a list of options, an editor, a guide, a confirmation."""

from collections.abc import Callable, Mapping, Sequence
from functools import partial

from . import toolkit
from .boards import Boards
from .cards import reflow
from .screen_types import Answer, Card
from .theme import BACK, CHIP_EXTRA, CHIP_HEIGHT, CHIP_WIDTH, ENTER, FEW_OPTIONS
from .toolkit import F2, Keys, Widget
from .widgets import Cards, at_top, is_key


class Modals(Boards):
    def show(
        self,
        title: str,
        markup: str,
        actions: Sequence[str] = (BACK,),
        keys: Sequence[int] = (),
        modal: bool = False,
    ) -> int | None:
        """A scrollable text (with colour markup) and a button per action: the index of the one pressed, or None. `keys`
        are the key codes of the first actions."""

        def build(answer: Answer) -> tuple[Widget, Keys | None]:
            lines = sum(max(1, len(line) // max(self._modal_size(0)[1] - 6, 1) + 1) for line in markup.split("\n"))
            frame = self._frame(title, modal=self._modal_size(lines + 3) if modal else None, scroll=False)
            main = toolkit.widgets.Layout([1], fill_frame=True)
            frame.add_layout(main)
            box = toolkit.widgets.TextBox(
                toolkit.widgets.Widget.FILL_FRAME,
                as_string=True,
                line_wrap=True,
                readonly=True,
                parser=toolkit.parsers.AsciimaticsParser(),
            )
            at_top(box)
            box.value = markup
            main.add_widget(box)
            self._buttons(frame, [(action, partial(answer.give, index)) for index, action in enumerate(actions)])
            foot = toolkit.widgets.Layout([1])
            frame.add_layout(foot)
            foot.add_widget(toolkit.widgets.Label("↑↓ desplazarse · Tab a los botones", align="^"))

            def pressed(event: Widget) -> None:
                for index, code in enumerate(keys):
                    if is_key(event, code):
                        answer.give(index)

            return frame, pressed

        result = self._play(build)
        return result if isinstance(result, int) else None

    def options(
        self,
        title: str,
        intro: str,
        options: Sequence[tuple[str, str]],
        chosen: Sequence[str],
        single: bool,
        search: bool = True,
        blocked: Callable[[Sequence[str]], Mapping[str, str]] | None = None,
    ) -> list[str] | None:
        """A modal of cards to choose from: the values chosen, or None to leave them as they were.

        With `search`, typing filters and «Usar lo escrito» takes the text itself. Without it, each card has its key.
        With `single`, choosing a card answers; otherwise Space, its key or a click mark it and Enter accepts what is
        marked (the highlighted one if nothing is). `blocked` says, for what is marked, which options can't be chosen
        and why (feature 062: a field incompatible with another one): their cards stay visible, locked, with it."""
        marked = list(chosen)

        def locked() -> Mapping[str, str]:
            return blocked(marked) if blocked is not None else {}

        def matching(text: str) -> list[tuple[str, str]]:
            needle = text.strip().lower()
            if not needle:
                return list(options)
            return [(v, d) for v, d in options if needle in v.lower() or needle in d.lower()]

        def build(answer: Answer) -> tuple[Widget, Keys | None]:
            width = self._modal_size(0)[1]
            widest = max((len(value) for value, _ in options), default=0) + CHIP_EXTRA
            # Few long values are shown whole; many of them keep two columns.
            chip_width = min(max(CHIP_WIDTH, widest), width - 4 if len(options) <= FEW_OPTIONS else (width - 6) // 2)
            per_row = max(1, (width - 2) // (chip_width + 2))
            rows = max(1, -(-len(options) // per_row))
            size = self._modal_size(rows * (CHIP_HEIGHT + 1) + 9)
            frame = self._frame(title, modal=size)
            top = toolkit.widgets.Layout([1])
            frame.add_layout(top)
            top.add_widget(self._help(intro, 3, size[1]))
            count = toolkit.widgets.Label("")

            def cards(text: str) -> list[Card]:
                shown = matching(text)
                count.text = (
                    f"{len(shown)} de {len(options)} · marcados: {', '.join(marked) or 'ninguno'}"
                    if options
                    else "No hay valores para sugerir: escribe uno y «Usar lo escrito»."
                )
                reasons = locked()
                return [Card(v, d, marked=v in marked, blocked=reasons.get(v, "")) for v, d in shown]

            def typed_text() -> str:
                return str(typed.value) if search else ""

            def highlighted(index: int) -> str | None:
                shown = matching(typed_text())
                return shown[index][0] if 0 <= index < len(shown) else None

            def toggle(index: int) -> None:
                value = highlighted(index)
                if value is not None:
                    if value in marked:
                        marked.remove(value)
                    else:
                        marked.append(value)
                    grid_box.set_cards(cards(typed_text()))

            def accept(index: int) -> None:
                value = highlighted(index)
                if single:
                    answer.give([value] if value is not None else list(marked))
                reasons = locked()
                kept = [value for value in marked if value not in reasons]
                answer.give(kept if kept or value is None or value in reasons else [value])

            typed: Widget = None

            def refilter() -> None:
                grid_box.index = 0
                grid_box.set_cards(cards(typed.value))

            def use_typed() -> None:
                text = typed.value.strip()
                if text and text not in marked:
                    if single:
                        marked.clear()
                    marked.append(text)
                answer.give(list(marked))

            search_index = 1
            if search:
                typed = toolkit.widgets.Text(label="buscar", name="search", on_change=lambda: None)
                top.add_widget(typed)
            top.add_widget(count)
            top.add_widget(toolkit.widgets.Divider())
            middle = toolkit.widgets.Layout([1], fill_frame=True)
            frame.add_layout(middle)
            grid_box: Widget = Cards(
                cards(""),
                accept,
                on_mark=None if single else toggle,
                height=CHIP_HEIGHT,
                min_width=chip_width,
                keys=not search,
            )
            if search:
                typed._on_change = refilter
            middle.add_widget(grid_box)
            buttons: list[tuple[str, Callable[[], None]]] = [("Enter Aceptar", lambda: accept(grid_box.index))]
            if search:
                buttons.append(("Usar lo escrito", use_typed))
                buttons.append(("Limpiar", lambda: answer.give([])))
            buttons.append((BACK, lambda: answer.give(None)))
            self._buttons(frame, buttons)
            hints = "escribe para filtrar" if search else "la tecla de cada tarjeta " + ("elige" if single else "marca")
            mark_hint = "Enter elige" if single else "Espacio marca · Enter acepta"
            foot = toolkit.widgets.Layout([1])
            frame.add_layout(foot)
            foot.add_widget(toolkit.widgets.Label(f"flechas moverse · {mark_hint} · {hints}", align="^"))
            self._after.append(lambda: frame.switch_focus(middle, 0, 0))

            def keys(event: Widget) -> None:
                if not search:
                    return
                if is_key(event, *ENTER) and frame.focussed_widget is typed:
                    accept(grid_box.index)
                elif (
                    isinstance(event, toolkit.events.KeyboardEvent)
                    and 32 < event.key_code < 256
                    and frame.focussed_widget is grid_box
                ):
                    frame.switch_focus(top, 0, search_index)  # typing goes to the search
                    typed.process_event(event)

            return frame, keys

        result = self._play(build)
        return [str(value) for value in result] if isinstance(result, list) else None

    def editor(self, title: str, text: str, check: Callable[[str], str | None]) -> str | None:
        """The JSON as edited (checked by `check`), or None to leave it as it was."""

        def build(answer: Answer) -> tuple[Widget, Keys | None]:
            frame = self._frame(title)
            main = toolkit.widgets.Layout([1], fill_frame=True)
            frame.add_layout(main)
            box = toolkit.widgets.TextBox(toolkit.widgets.Widget.FILL_FRAME, as_string=True, name="body")
            at_top(box)
            box.value = text
            main.add_widget(box)
            message = toolkit.widgets.Label("", height=2)
            foot = toolkit.widgets.Layout([1])
            frame.add_layout(foot)
            foot.add_widget(toolkit.widgets.Divider())
            foot.add_widget(message)

            def save() -> None:
                problem = check(box.value)
                if problem:
                    message.text = f"✗ {problem}"
                else:
                    answer.give(box.value)

            self._buttons(frame, [("F2 Guardar", save), (BACK, lambda: answer.give(None))])

            def keys(event: Widget) -> None:
                if is_key(event, toolkit.screen.Screen.KEY_F2):
                    save()

            return frame, keys

        edited = self._play(build)
        return edited if isinstance(edited, str) else None

    def guide(self, title: str, markup: str) -> None:
        """A long explanation, over the screen it helps with."""
        self.show(title, reflow(markup, self._modal_size(0)[1] - 6), modal=True)

    def confirm(self, title: str, text: str) -> bool:
        """F2 sends; Esc or «Cancelar» don't."""
        pressed = self.show(title, text, ("F2 Enviar", "Esc Cancelar"), (F2,), modal=True)
        return pressed == 0
