"""What every dialog of the console is made of: its frame, its buttons, its banner and its own loop of frames, instead
of Screen.play, so that one of them (a run's progress) can refresh itself between frames without threads.

A modal is a smaller frame drawn over the previous screen, which is left on the buffer and dimmed."""

import signal
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from types import FrameType
from typing import Self

from . import toolkit
from .screen_types import Answer
from .theme import BANNER, BANNER_FONT, BANNER_MIN_HEIGHT, BLACK, DIM, FRAME_TIME, PALETTE, WHITE
from .toolkit import Keys, Widget
from .widgets import is_key, rounded


def open_screen() -> Widget:
    """The terminal for asciimatics, whose resize handler calls endwin() + initscr() inside the signal: dragging the
    window sends a burst, and a second endwin() in a row raises curses.error. Here the signal only marks the screen as
    resized and the loop of frames reopens it, outside the signal. Blocked while opening, so that the handler of the
    library never runs: what arrives meanwhile is delivered to the new one. Screen.close restores the previous one."""
    resize = getattr(signal, "SIGWINCH", None)  # Windows has no such signal: it isn't handled this way there
    if resize is None:
        return toolkit.screen.Screen.open()
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, {resize})
    try:
        screen = toolkit.screen.Screen.open()

        def mark(_number: int, _frame: FrameType | None) -> None:
            screen._re_sized = True  # what has_resized() reads; the library has no other way in

        signal.signal(resize, mark)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)
    return screen


class ScreenBase:
    def __init__(self, screen: Widget) -> None:
        self._screen = screen
        self.trail: list[str] = []  # where the user is, shown as a breadcrumb on top of every screen
        self._after: list[Callable[[], None]] = []  # run once the scene started (it resets focus and lists)
        self._behind: list[tuple[int, int, str, int, int, int]] | None = None  # the dimmed cells behind the modals
        self.status: Callable[[], str] = lambda: ""  # the services, asked each time a screen opens (feature 039)

    @classmethod
    @contextmanager
    def opened(cls) -> Iterator[Self]:
        """The whole terminal for the console; restored when leaving (also on an error or Ctrl+C)."""
        screens = cls(open_screen())
        try:
            yield screens
        finally:
            screens._screen.close()

    @property
    def width(self) -> int:
        return int(self._screen.width)

    def _frame(self, title: str, scroll: bool = False, modal: tuple[int, int] | None = None) -> Widget:
        """The whole screen with the breadcrumb on top or, with `modal` (height, width), a window over what is there."""
        if modal is None:
            self._behind = None
            frame = toolkit.widgets.Frame(
                self._screen, self._screen.height, self._screen.width, title=f" {title} ", can_scroll=scroll
            )
        else:
            self._keep_behind()
            height, width = modal
            frame = toolkit.widgets.Frame(
                self._screen,
                height,
                width,
                title=f" {title} ",
                x=(self._screen.width - width) // 2,
                y=(self._screen.height - height) // 2,
                has_shadow=True,
                can_scroll=scroll,
            )
        frame.palette = PALETTE
        rounded(frame)
        if modal is None:
            crumbs = toolkit.widgets.Layout([1])
            frame.add_layout(crumbs)
            crumbs.add_widget(toolkit.widgets.Label(" ▸ ".join(["inicio", *self.trail])))
            status = toolkit.widgets.Label(self.status())
            status.custom_colour = "label"
            crumbs.add_widget(status)
            crumbs.add_widget(toolkit.widgets.Divider())
        return frame

    def _keep_behind(self) -> None:
        """Dims and keeps what is on the screen the first time: _play puts it back for every modal, so that closing one
        that was open over another one leaves nothing behind."""
        screen = self._screen
        if self._behind is None:
            screen.highlight(0, 0, screen.width, screen.height, fg=DIM if screen.colours >= 256 else WHITE, bg=BLACK)
            self._behind = []
            for y in range(screen.height):
                for x in range(screen.width):
                    cell = screen.get_from(x, y)
                    if cell is not None:
                        self._behind.append((x, y, chr(cell[0]), cell[1], cell[2], cell[3]))

    def _modal_size(self, lines: int) -> tuple[int, int]:
        """(height, width) of a modal with that many lines inside."""
        width = min(self._screen.width - 4, max(72, self._screen.width * 3 // 4))
        return min(self._screen.height - 2, lines + 2), max(width, 20)

    def _buttons(self, frame: Widget, actions: Sequence[tuple[str, Callable[[], None]]]) -> None:
        """Rows of buttons, each as wide as its text; a new row when the next one wouldn't fit."""
        rows: list[list[tuple[str, Callable[[], None]]]] = [[]]
        used = 0
        for item in actions:
            needed = len(item[0]) + 6
            if rows[-1] and used + needed > frame.canvas.width:
                rows.append([])
                used = 0
            rows[-1].append(item)
            used += needed
        for buttons in rows:
            widths = [len(label) + 6 for label, _ in buttons]
            row = toolkit.widgets.Layout([*widths, max(1, frame.canvas.width - sum(widths))])
            frame.add_layout(row)
            for column, (label, action) in enumerate(buttons):
                button = toolkit.widgets.Button(label, action)
                button._text = f"[ {label} ]"  # its box, with the square brackets of the cards' keys, not chevrons
                row.add_widget(button, column)

    def _banner(self) -> Widget | None:
        """The big title, when it fits."""
        if self._screen.height < BANNER_MIN_HEIGHT:
            return None
        lines = toolkit.renderers.FigletText(BANNER, font=BANNER_FONT, width=self._screen.width).rendered_text[0]
        lines = [line.rstrip() for line in lines if line.strip()]
        widest = max((len(line) for line in lines), default=0)
        if not lines or widest > self._screen.width - 4:
            return None
        label = toolkit.widgets.Label("\n".join(line.ljust(widest) for line in lines), height=len(lines), align="^")
        label.custom_colour = "label"
        return label

    def _play(
        self, build: Callable[[Answer], tuple[Widget, Keys | None]], tick: Callable[[], None] | None = None
    ) -> object:
        """Shows the frame `build` makes until it answers (Esc: None, unless its keys swallow it). `tick` runs between
        frames. A resized terminal reopens the screen and rebuilds the frame."""
        answer = Answer()
        while True:
            frame, keys = build(answer)
            frame.fix()

            def unhandled(event: Widget, keys: Keys | None = keys) -> None:
                if keys is not None:
                    keys(event)
                if is_key(event, toolkit.screen.Screen.KEY_ESCAPE):
                    answer.give(None)

            self._screen.set_scenes([toolkit.scene.Scene([frame], -1)], unhandled_input=unhandled)
            for x, y, char, colour, attr, background in self._behind or ():  # set_scenes always clears the screen
                self._screen.print_at(char, x, y, colour, attr, background)
            for after in self._after:  # starting the scene resets the focus to the first widget
                after()
            self._after = []
            try:
                while True:
                    if tick is not None:
                        tick()
                    self._screen.draw_next_frame()
                    if self._screen.has_resized():
                        raise toolkit.exceptions.ResizeScreenError("resized")
                    self._screen.wait_for_input(FRAME_TIME)
            except toolkit.exceptions.StopApplication:
                return answer.value
            except toolkit.exceptions.ResizeScreenError:
                self._screen.close()
                self._screen = open_screen()
                self._behind = None

    def _wrapped(self, text: str, width: int | None = None) -> int:
        """The lines a text takes in a frame of that width."""
        inner = max((width or self.width) - 4, 20)
        return sum(max(1, -(-len(line) // inner)) for line in text.split("\n"))

    def _help(self, text: str, height: int, width: int | None = None) -> Widget:
        """Text that never takes the focus, wrapped and shown from its first line (the rest is cut)."""
        return toolkit.widgets.Label(text, height=max(1, min(self._wrapped(text, width), height)))
