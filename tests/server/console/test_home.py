"""The console's home: a card per module of MODULES, each with its summary (a module without one broke the console)."""

from server.console.app import Console
from server.console.catalog import MODULES
from server.console.client import ApiClient
from server.console.settings import ConsoleSettings
from server.console.web_front import WEB


def _home(client: ApiClient) -> Console:
    console = Console.__new__(Console)  # only what the home reads: the client, the settings and the cached health
    console._client, console._state, console._state_at = client, None, 0.0
    console._settings = ConsoleSettings("http://127.0.0.1:8000", "neo4j://n", "neo4j", "neo4j")
    return console


def test_every_module_has_a_card_with_a_summary(client: ApiClient) -> None:
    cards = {card.title: card for card in _home(client)._home_items()}
    assert all(module.name in cards and cards[module.name].text for module in MODULES)


def test_the_web_card_comes_right_after_the_modules_and_names_its_url(client: ApiClient) -> None:
    cards = _home(client)._home_items()
    web = cards[len(MODULES) + 1]  # main() opens the web front for this index
    assert (web.title, "http://127.0.0.1:8000/web/" in web.help) == (WEB, True)
