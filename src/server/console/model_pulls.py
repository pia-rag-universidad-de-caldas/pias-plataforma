"""The admitted LLM models that Ollama doesn't have yet, pulled in the background once the server is up (feature 054),
through the llm module's API: GET /llm/models and POST /llm/models/pull. Without /llm, nothing is pulled and the home
screen says so; the progress is a line of that screen."""

import threading
import time
from collections.abc import Callable

from .bodies import JsonValue
from .client import ApiClient, ServerError
from .requests import PreparedRequest

MODELS = "/llm/models"
PULL = "/llm/models/pull"
PULLS = "/llm/models/pulls"
POLL = 2.0  # seconds between two looks at a pull
OLLAMA_WAIT = 180.0  # seconds a pull is retried while Ollama (just started) can't take it
FINISHED = frozenset({"done", "finished", "success", "completed", "installed"})
FAILED = frozenset({"failed", "error", "cancelled", "canceled"})


def missing(models: JsonValue) -> list[str]:
    """The admitted models not installed, from GET /llm/models."""
    admitted = models.get("admitted") if isinstance(models, dict) else None
    listed = admitted if isinstance(admitted, list) else []
    return [
        str(model["name"])
        for model in listed
        if isinstance(model, dict) and isinstance(model.get("name"), str) and model.get("installed") is False
    ]


def progress(pull: JsonValue) -> str:
    """A pull's state in a few words: its status and, if it says so, how much is done."""
    if not isinstance(pull, dict):
        return "?"
    status = str(pull.get("status") or "?")
    completed, total = pull.get("completed"), pull.get("total")
    if isinstance(completed, int | float) and isinstance(total, int | float) and total > 0:
        return f"{status} {completed / total:.0%}"
    share = pull.get("progress")
    if isinstance(share, int | float):
        return f"{status} {share:.0%}" if share <= 1 else f"{status} {share:.0f}%"
    return status


class ModelPulls:
    """A thread that pulls the missing models one after another; `line` says how it goes (in Spanish)."""

    def __init__(
        self,
        client: ApiClient,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._sleep = sleep
        self._clock = clock
        self._lock = threading.Lock()
        self._line = ""
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def line(self) -> str:
        with self._lock:
            return self._line

    def _say(self, line: str) -> None:
        with self._lock:
            self._line = line

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, name="model-pulls", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()

    def _wait(self, seconds: float) -> bool:
        """Sleeps; False once the console is leaving."""
        self._sleep(seconds)
        return not self._stopped.is_set()

    def _pull(self, name: str, position: str) -> bool:
        """Pulls one model; whether it ended installed."""
        deadline = self._clock() + OLLAMA_WAIT
        while True:
            try:
                answer = self._client.send(PreparedRequest("POST", PULL, (), {"name": name}, True))
            except ServerError:  # the server is gone: the console is leaving
                return False
            if answer.ok:
                break
            if answer.status < 500 or self._clock() >= deadline:
                self._say(f"modelos: {name} no se pudo pedir ({answer.status})")
                return False
            self._say(f"modelos: esperando a Ollama para descargar {name}...")
            if not self._wait(POLL):
                return False
        pull = answer.data
        pull_id = pull.get("id") if isinstance(pull, dict) else None
        while pull_id is not None:
            state = progress(pull)
            status = state.split()[0].lower()
            if status in FINISHED:
                return True
            if status in FAILED:
                error = pull.get("error") if isinstance(pull, dict) else None
                self._say(f"modelos: {name} falló{f': {error}' if error else ''}")
                return False
            self._say(f"modelos: descargando {name} {position} · {state}")
            if not self._wait(POLL):
                return False
            pull = self._client.get_json(f"{PULLS}/{pull_id}", {})
            if pull is None:
                return False
        return True

    def run(self) -> None:
        models = self._client.get_json(MODELS, {})
        if not isinstance(models, dict):
            self._say("modelos: /llm no responde; no se descargan modelos")
            return
        names = missing(models)
        if not names:
            self._say("modelos: todos los admitidos están descargados")
            return
        done = 0
        for number, name in enumerate(names, 1):
            if self._stopped.is_set():
                return
            done += self._pull(name, f"({number}/{len(names)})")
        failed = len(names) - done
        if not self._stopped.is_set():
            ending = f"; {failed} no" if failed else ""
            self._say(f"modelos: {done} de {len(names)} descargados{ending}")
