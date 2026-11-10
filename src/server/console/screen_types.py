"""What the dialogs of the console take and answer: cards, buttons, form fields and the events they give back."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from . import toolkit
from .toolkit import Widget


@dataclass(frozen=True)
class Card:
    title: str
    text: str = ""  # wrapped under the title
    help: str = ""  # under the grid while it is highlighted
    verb: str = ""  # an HTTP method, in its colour
    status: bool | None = None  # ● or ✗
    alert: bool = False  # its text deserves attention
    marked: bool | None = None  # None: it can't be marked
    blocked: str = ""  # why it can't be used now: it stays visible but doesn't answer (feature 039)


@dataclass(frozen=True)
class Button:
    """A button of a board: pressing it or its key answers BoardEvent(key)."""

    key: str
    label: str


@dataclass(frozen=True)
class BoardEvent:
    kind: str  # "card", "back" or the key of a Button
    index: int = -1


@dataclass(frozen=True)
class FlowEvent:
    kind: str  # "edit" (Enter), "back" or the key of a Button
    stage: str | None = None  # the one highlighted


@dataclass(frozen=True)
class FormField:
    name: str
    label: str
    value: str
    kind: Literal["text", "check", "choice", "suggest", "object"] = "text"
    choices: tuple[str, ...] = ()
    optional: bool = True  # a drop-down with an empty first option
    preview: Callable[[str], str] | None = None  # what to say about the value while it is typed


@dataclass(frozen=True)
class FormActions:
    optional_count: int  # optional fields the action has (in use or not)
    json: bool  # it has a body that can be edited as JSON
    guide: bool = False  # it has a guide (F6)
    send: str = "Enviar"


@dataclass(frozen=True)
class FormEvent:
    kind: Literal["send", "back", "pick", "json", "add", "remove", "help"]
    values: Mapping[str, str] = field(default_factory=dict)
    field: str = ""  # the one whose list was asked for


@dataclass(frozen=True)
class TableEvent:
    kind: Literal["row", "previous", "next", "json", "back"]
    row: int = -1


class Answer:
    """What the dialog answered; set right before raising StopApplication."""

    def __init__(self) -> None:
        self.value: object = None

    def give(self, value: object) -> None:
        self.value = value
        raise toolkit.exceptions.StopApplication("answered")


class Refresh:
    """The state of a self-refreshing screen between frames."""

    def __init__(self) -> None:
        self.box: Widget = None
        self.next = 0.0
        self.done = False
