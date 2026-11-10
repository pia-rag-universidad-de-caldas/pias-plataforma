"""The console's home: a card per module of MODULES, each with its summary (a module without one broke the console)."""

from server.console.app import Console
from server.console.catalog import MODULES
from server.console.client import ApiClient


def test_every_module_has_a_card_with_a_summary(client: ApiClient) -> None:
    console = Console.__new__(Console)  # only what the home reads: the client and the cached health
    console._client, console._state, console._state_at = client, None, 0.0
    cards = {card.title: card for card in console._home_items()}
    assert all(module.name in cards and cards[module.name].text for module in MODULES)
