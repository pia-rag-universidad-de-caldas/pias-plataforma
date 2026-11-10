"""screen_base: a burst of resize signals must never run curses inside a signal (a second endwin() raises)."""

import os
import signal
from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from server.console import toolkit
from server.console.screen_base import open_screen


class FakeScreen:
    """Like asciimatics: opening it installs a resize handler that would touch curses."""

    curses_calls = 0

    def __init__(self) -> None:
        self._re_sized = False
        signal.signal(signal.SIGWINCH, self._touches_curses)
        os.kill(os.getpid(), signal.SIGWINCH)  # the window is dragged while it opens

    def _touches_curses(self, _number: int, _frame: object) -> None:
        FakeScreen.curses_calls += 1


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeScreen]:
    FakeScreen.curses_calls = 0
    previous = signal.getsignal(signal.SIGWINCH)
    monkeypatch.setattr(toolkit, "screen", SimpleNamespace(Screen=SimpleNamespace(open=FakeScreen)))
    yield open_screen()
    signal.signal(signal.SIGWINCH, previous)


def test_a_resize_while_opening_never_reaches_the_handler_of_the_library(opened: FakeScreen) -> None:
    assert FakeScreen.curses_calls == 0


def test_a_resize_while_opening_is_not_lost(opened: FakeScreen) -> None:
    assert opened._re_sized


def test_a_resize_after_opening_only_marks_the_screen(opened: FakeScreen) -> None:
    opened._re_sized = False
    os.kill(os.getpid(), signal.SIGWINCH)
    assert opened._re_sized
    assert FakeScreen.curses_calls == 0


def test_the_mask_of_signals_is_left_as_it_was(opened: FakeScreen) -> None:
    assert signal.SIGWINCH not in signal.pthread_sigmask(signal.SIG_BLOCK, set())
