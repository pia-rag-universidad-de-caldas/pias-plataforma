"""The web front from the console: its URLs and the console actions that open it instead of a form."""

from server.console.web_front import SCREENS, web_screen, web_url


def test_web_url_points_at_the_web_and_its_screen() -> None:
    assert [web_url("http://127.0.0.1:8000/"), web_url("http://127.0.0.1:8000", "chat")] == [
        "http://127.0.0.1:8000/web/",
        "http://127.0.0.1:8000/web/#chat",
    ]


def test_asking_in_consultas_opens_the_web_chat() -> None:
    screen = web_screen("consultas", "ask")
    assert screen is not None and screen.hash == "chat"


def test_other_resources_keep_their_form() -> None:
    assert [web_screen("consultas", "search"), web_screen("llm", "ask")] == [None, None]


def test_the_screens_are_the_ones_the_web_routes() -> None:
    assert [s.hash for s in SCREENS] == ["chat", "comparar", "carga"]  # web/src/main.js: screens
