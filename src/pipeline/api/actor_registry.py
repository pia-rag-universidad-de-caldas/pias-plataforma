"""ActorRegistry: the actors this server knows and their callback_url (in memory: they are configuration; the known
ones of config.ACTORS start without URL)."""

import threading

from pipeline.config import ACTORS
from pipeline.models import Actor


class ActorRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._actors = {name: Actor(name) for name in ACTORS}

    def all(self) -> list[Actor]:
        with self._lock:
            return sorted(self._actors.values(), key=lambda a: a.name)

    def get(self, name: str) -> Actor:
        """The actor (one never registered has no callback_url)."""
        with self._lock:
            return self._actors.get(name, Actor(name))

    def put(self, actor: Actor) -> Actor:
        with self._lock:
            self._actors[actor.name] = actor
            return actor
