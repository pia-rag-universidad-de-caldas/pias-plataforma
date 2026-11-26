"""How the console looks: its colours, sizes and texts, and the asciimatics ${fg,attr} markup (feature 037, dark theme
with blue cards and buttons)."""

import json
import re

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)
BOLD, NORMAL = 1, 2
ENTER = (10, 13)
SPACE = 32
FRAME_TIME = 0.05
HELP_HEIGHT = 2
EMPTY = "(vacío)"
DIM = 240  # what is behind a modal, in a 256-colour terminal
BANNER = "prueba-chunking"
BANNER_FONT = "slant"
BANNER_MIN_HEIGHT = 30
CARD_HEIGHT = 6
SHORT_CARD_HEIGHT = 5  # in a short terminal
SHORT_SCREEN = 30
CARD_WIDTH = 30
CHIP_HEIGHT = 4  # the cards of a modal
CHIP_WIDTH = 26
HOME_SHORT_WIDTH = 24  # three columns in 80: the home screen shows all of its cards and the way out
CHIP_EXTRA = 10  # what a card of a modal adds to its title: border, key and mark
FEW_OPTIONS = 6
BACK = "Esc ← Volver"

# Dark theme with blue cards and buttons (feature 037, after 404_Luck_Not_Found_Cliente).
PALETTE: dict[str, tuple[int, int, int]] = {
    "background": (WHITE, NORMAL, BLACK),
    "shadow": (BLACK, NORMAL, BLACK),
    "disabled": (WHITE, NORMAL, BLACK),
    "invalid": (RED, BOLD, BLACK),
    "label": (CYAN, BOLD, BLACK),
    "borders": (BLUE, BOLD, BLACK),
    "scroll": (CYAN, NORMAL, BLACK),
    "title": (WHITE, BOLD, BLUE),
    "edit_text": (WHITE, NORMAL, BLACK),
    "focus_edit_text": (BLACK, NORMAL, CYAN),
    "readonly": (WHITE, NORMAL, BLACK),
    "focus_readonly": (WHITE, NORMAL, BLACK),
    "button": (WHITE, BOLD, BLUE),
    "focus_button": (BLACK, NORMAL, CYAN),
    "control": (YELLOW, NORMAL, BLACK),
    "selected_control": (YELLOW, BOLD, BLACK),
    "focus_control": (BLACK, NORMAL, CYAN),
    "selected_focus_control": (BLACK, NORMAL, CYAN),
    "field": (WHITE, NORMAL, BLACK),
    "selected_field": (CYAN, BOLD, BLACK),
    "focus_field": (WHITE, NORMAL, BLACK),
    "selected_focus_field": (BLACK, NORMAL, CYAN),
}
METHOD_COLOURS = {"GET": GREEN, "POST": YELLOW, "PUT": YELLOW, "PATCH": YELLOW, "DELETE": MAGENTA}
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
