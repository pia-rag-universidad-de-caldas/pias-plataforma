"""The progress screen of data (features 042 and 043): what each card and its list of missing ones say."""

from server.console.bodies import JsonObject
from server.console.coverage import STAGES, card, missing_text

PARSING, CHUNKING = STAGES
BODY: JsonObject = {"total": 10, "done": 4, "missing": 6, "partial": 1, "errors": 2, "never": 3, "sha256s": ["a", "b"]}


def test_a_card_has_its_bar_and_why_some_are_missing() -> None:
    found = card(PARSING, BODY)
    assert "40%" in found.text and "4 de 10 parseados" in found.text
    assert "1 parciales" in found.text and "2 con error" in found.text and "3 sin intentar" in found.text
    assert found.alert and found.status is None


def test_chunking_has_no_partial_ones() -> None:
    assert "parciales" not in card(CHUNKING, BODY).text


def test_everything_done_is_marked() -> None:
    assert card(CHUNKING, {"total": 3, "done": 3, "missing": 0}).status is True


def test_data_down_is_said() -> None:
    assert card(PARSING, None).status is False


def test_the_missing_ones_say_there_are_more() -> None:
    text = missing_text(PARSING, BODY)
    assert text.splitlines()[2:4] == ["a", "b"] and "y 4 más" in text


def test_nothing_missing_is_said() -> None:
    assert "No falta ninguno" in missing_text(CHUNKING, {"missing": 0, "sha256s": []})
