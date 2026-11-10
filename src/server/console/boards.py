"""The screens made of cards: a board, a menu and the flow diagram of a template (feature 039)."""

from collections.abc import Callable, Sequence
from functools import partial

from . import toolkit
from .flow import Diagram
from .screen_base import ScreenBase
from .screen_types import Answer, BoardEvent, Button, Card, FlowEvent, Refresh
from .theme import (
    BACK,
    CARD_HEIGHT,
    CARD_WIDTH,
    CHIP_HEIGHT,
    CHIP_WIDTH,
    HELP_HEIGHT,
    HOME_SHORT_WIDTH,
    SHORT_CARD_HEIGHT,
    SHORT_SCREEN,
)
from .toolkit import Keys, Widget
from .widgets import Cards, Flow, is_key


class Boards(ScreenBase):
    def board(
        self,
        title: str,
        intro: str,
        cards: Sequence[Card],
        selected: int = 0,
        buttons: Sequence[Button] = (),
        escape: bool = True,
        banner: bool = False,
        modal: bool = False,
        empty: str = "",
        refresh: Callable[[], tuple[Sequence[Card], str] | None] | None = None,
        card_width: int = CARD_WIDTH,
    ) -> BoardEvent:
        """Cards to choose from (each with its key; its help shown while highlighted) and buttons with a key. Every
        board has a button to go back, unless `escape` is off (the home screen, which has its card to leave). With
        `modal`, a window over the previous screen that shows its whole `intro`; `empty` is said when there are no
        cards. `refresh` runs between frames: what it gives (cards and intro) replaces what is shown."""
        live = Refresh()

        def build(answer: Answer) -> tuple[Widget, Keys | None]:
            size = None
            intro_lines = 3
            if modal:
                width = self._modal_size(0)[1]
                intro_lines = self._wrapped(intro, width)
                per_row = max(1, (width - 2) // (CHIP_WIDTH + 2))
                rows = max(1, -(-len(cards) // per_row))
                size = self._modal_size(intro_lines + rows * (CHIP_HEIGHT + 1) + HELP_HEIGHT + 5)
            frame = self._frame(title, modal=size)
            top = toolkit.widgets.Layout([1], fill_frame=True)
            frame.add_layout(top)
            big = self._banner() if banner else None
            if big is not None:
                top.add_widget(big)
            intro_box = None
            short = self._screen.height < SHORT_SCREEN and not modal
            if intro and not (banner and short):  # the home screen must show its way out
                intro_box = self._help(intro, intro_lines, size[1] if size else None)
                if refresh is not None:  # what comes later may take more lines
                    intro_box = toolkit.widgets.Label(intro, height=intro_lines)
                top.add_widget(intro_box)
                top.add_widget(toolkit.widgets.Divider())
            help_box = toolkit.widgets.Label("", height=HELP_HEIGHT)
            card_height = CHIP_HEIGHT if modal else CARD_HEIGHT
            min_width = CHIP_WIDTH if modal else HOME_SHORT_WIDTH if banner and short else card_width
            if short:
                card_height = CHIP_HEIGHT if banner else SHORT_CARD_HEIGHT
                if card_width != CARD_WIDTH:  # wide cards: more of them seen, with one line each
                    card_height, min_width = CHIP_HEIGHT, self.width - 4

            def changed(index: int) -> None:
                shown = grid_box.cards
                card = shown[index] if index < len(shown) else None
                help_box.text = (card.blocked or card.help) if card is not None else ""

            grid_box: Widget = Cards(
                cards,
                lambda index: answer.give(BoardEvent("card", index)),
                on_change=changed,
                height=card_height,
                min_width=min_width,
                reserved="".join(button.key for button in buttons),
            )
            grid_box.empty = empty
            top.add_widget(grid_box)
            grid_box.index = min(selected, max(len(cards) - 1, 0))
            changed(grid_box.index)

            def renew(fresh: tuple[Sequence[Card], str]) -> None:
                grid_box.set_cards(fresh[0])
                changed(grid_box.index)
                if intro_box is not None:
                    intro_box.text = fresh[1]

            live.box = renew
            bottom = toolkit.widgets.Layout([1])
            frame.add_layout(bottom)
            bottom.add_widget(toolkit.widgets.Divider())
            bottom.add_widget(help_box)
            actions: list[tuple[str, Callable[[], None]]] = [
                (f"{button.key} {button.label}", partial(answer.give, BoardEvent(button.key))) for button in buttons
            ]
            if escape:
                actions.append((BACK, lambda: answer.give(BoardEvent("back"))))
            if actions:
                self._buttons(frame, actions)
            hint = toolkit.widgets.Layout([1])
            frame.add_layout(hint)
            hint.add_widget(toolkit.widgets.Label("flechas · Enter, ratón o tecla: elegir · Tab: botones", align="^"))

            def keys(event: Widget) -> None:
                if not escape and is_key(event, toolkit.screen.Screen.KEY_ESCAPE):
                    event.key_code = 0  # swallowed: Esc doesn't leave this screen
                for button in buttons:
                    if is_key(event, ord(button.key)):
                        answer.give(BoardEvent(button.key))

            return frame, keys

        def tick() -> None:
            fresh = refresh() if refresh is not None else None
            if fresh is not None:
                live.box(fresh)
                self._screen.force_update()  # without an event, asciimatics doesn't draw again

        chosen = self._play(build, tick if refresh is not None else None)
        return chosen if isinstance(chosen, BoardEvent) else BoardEvent("back")

    def flow(
        self,
        title: str,
        intro: str,
        diagram: Diagram,
        selected: str | None,
        explain: Callable[[str], str],
        buttons: Sequence[Button],
        problem: str = "",
    ) -> FlowEvent:
        """A flow diagram: ↑↓ or the mouse go from stage to stage (it scrolls by itself), Enter edits the highlighted
        one and each button answers with its key."""

        def build(answer: Answer) -> tuple[Widget, Keys | None]:
            frame = self._frame(title)
            top = toolkit.widgets.Layout([1], fill_frame=True)
            frame.add_layout(top)
            top.add_widget(self._help(intro, 2))
            box: Widget = Flow(diagram, selected, lambda: answer.give(FlowEvent("edit", box.selected)))
            top.add_widget(box)
            bottom = toolkit.widgets.Layout([1])
            frame.add_layout(bottom)
            bottom.add_widget(toolkit.widgets.Divider())
            about = toolkit.widgets.Label(explain(box.selected) if box.selected else "", height=HELP_HEIGHT)
            bottom.add_widget(about)
            message = toolkit.widgets.Label(
                f"✗ {problem}" if problem else "✓ Estas etapas pueden correr en este orden.", height=2
            )
            message.custom_colour = "invalid" if problem else "label"
            bottom.add_widget(message)

            def moved(id: str) -> None:
                about.text = explain(id)

            box.on_change = moved
            actions: list[tuple[str, Callable[[], None]]] = [
                (f"{b.key} {b.label}", partial(lambda k: answer.give(FlowEvent(k, box.selected)), b.key))
                for b in buttons
            ]
            actions.append((BACK, lambda: answer.give(FlowEvent("back"))))
            self._buttons(frame, actions)
            hint = toolkit.widgets.Layout([1])
            frame.add_layout(hint)
            hint.add_widget(
                toolkit.widgets.Label("↑↓ o ratón: elegir etapa · Enter: editarla · Tab: botones", align="^")
            )

            def keys(event: Widget) -> None:
                for button in buttons:
                    if is_key(event, ord(button.key)):
                        answer.give(FlowEvent(button.key, box.selected))

            return frame, keys

        result = self._play(build)
        return result if isinstance(result, FlowEvent) else FlowEvent("back")

    def menu(self, title: str, intro: str, cards: Sequence[Card], selected: int = 0) -> int | None:
        """The index of the card chosen, or None to go back."""
        event = self.board(title, intro, cards, selected)
        return event.index if event.kind == "card" else None
