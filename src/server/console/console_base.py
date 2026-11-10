"""What every part of the console shares: the client, the screens, what was typed in this session and the services."""

import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from .bodies import JsonObject
from .catalog import Operation
from .client import ApiClient
from .flow_editor import TemplateEditor
from .health import Health, read_health
from .model_pulls import ModelPulls
from .screens import Screens
from .server_process import ServerProcess
from .settings import ConsoleSettings
from .suggestions import Suggester

HEALTH_CACHE = 1.0  # seconds: a screen's cards and its status line are the same look at the services


class ConsoleBase:
    def __init__(
        self,
        client: ApiClient,
        screens: Screens,
        settings: ConsoleSettings,
        started: str,
        server: ServerProcess,
        models: ModelPulls | None = None,
    ) -> None:
        self._client = client
        self._screens = screens
        self._settings = settings
        self._started = started  # what the console did to get ready, shown in «estado»
        self._server = server
        self._models = models  # the LLM models pulled in the background (feature 054), shown on the home screen
        self._typed: dict[tuple[str, str, str], str] = {}  # (module, resource, field) → last value typed
        self._bodies: dict[tuple[str, str, str], JsonObject] = {}  # last body sent per operation
        self._recent: dict[tuple[str, str], list[str]] = {}  # (module, resource) → ids created, newest first
        self._suggester = Suggester(client, self._recent)
        self._operations: dict[str, tuple[Operation, ...]] = {}
        self._state: Health | None = None
        self._state_at = 0.0
        self._templates = TemplateEditor(client, screens)
        screens.status = lambda: self._health().line

    def _health(self) -> Health:
        """The services now: asked at every step of the navigation (feature 039)."""
        if self._state is None or time.monotonic() - self._state_at >= HEALTH_CACHE:
            self._state, self._state_at = read_health(self._client), time.monotonic()
        return self._state

    @contextmanager
    def _at(self, place: str) -> Iterator[None]:
        """One more step of the breadcrumb shown on top of every screen."""
        self._screens.trail.append(place)
        try:
            yield
        finally:
            self._screens.trail.pop()

    def _run(self, operation: Operation, preset: Mapping[str, str] | None = None) -> None:
        """A route's form, up to its answer: implemented by `FormFlow`, asked for from a row of a table."""
        raise NotImplementedError
