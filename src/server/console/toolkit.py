"""asciimatics: the only file that loads it. It has no types, so it is loaded with import_module and is Any from here on
(like Docling in chunking/adapters/)."""

from collections.abc import Callable
from importlib import import_module
from typing import Any

type Widget = Any  # an asciimatics object (screen, frame, widget, event): the library is untyped
type Keys = Callable[[Widget], None]

widgets = import_module("asciimatics.widgets")
scene = import_module("asciimatics.scene")
screen = import_module("asciimatics.screen")
events = import_module("asciimatics.event")
exceptions = import_module("asciimatics.exceptions")
parsers = import_module("asciimatics.parsers")
renderers = import_module("asciimatics.renderers")

F2 = screen.Screen.KEY_F2
