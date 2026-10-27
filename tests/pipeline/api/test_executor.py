"""Executor (feature 028): the `piaa` template end to end with fake ports (no server): the module queues, the waits,
the answers, the score sent to the iteration's experiment, the notifications and cancel/resume."""

import threading
import time

import pytest

from pipeline.api.actor_registry import ActorRegistry
from pipeline.api.executor import Executor, now
from pipeline.domain import PIAA, Engine
from pipeline.models import (
    Actor,
    ChunkingPort,
    Completion,
    ConflictError,
    DataPort,
    Decision,
    DecisionKind,
    ExperimentOutcome,
    IdPage,
    IngestaPort,
    JsonObject,
    Modules,
    Notifier,
    PipelineRun,
    Promotion,
    RunRequest,
    RunStatus,
    RunStore,
    Selection,
    SourcePage,
    Template,
)


class MemoryStore(RunStore):
    def __init__(self) -> None:
        self.saved_templates: dict[str, Template] = {}
        self.saved_runs: dict[str, PipelineRun] = {}
        self.created: list[str] = []

    def templates(self) -> list[Template]:
        return list(self.saved_templates.values())

    def template(self, id: str) -> Template | None:
        return self.saved_templates.get(id)

    def save_template(self, template: Template) -> None:
        self.saved_templates[template.id] = template

    def delete_template(self, id: str) -> bool:
        return self.saved_templates.pop(id, None) is not None

    def runs(self) -> list[PipelineRun]:
        return list(self.saved_runs.values())

    def run(self, id: str) -> PipelineRun | None:
        return self.saved_runs.get(id)

    def save_run(self, run: PipelineRun, created: bool = False) -> None:
        if created:
            self.created.append(run.id)
        self.saved_runs[run.id] = run


class FakeIngesta(IngestaPort):
    def __init__(self) -> None:
        self.files = [f"sha{i}" for i in range(7)]
        self.asked: list[tuple[int, int]] = []

    def page(self, selection: Selection, page: int, per_page: int) -> SourcePage:
        self.asked.append((page, per_page))
        pages = -(-len(self.files) // per_page)
        return SourcePage(tuple(self.files[(page - 1) * per_page : page * per_page]), pages, "2026-10-01")

    def has(self, sha256: str) -> bool:
        return sha256 in self.files


class FakeChunking(ChunkingPort):
    def __init__(self) -> None:
        self.bodies: list[JsonObject] = []
        self.scores: list[tuple[str, JsonObject]] = []
        self.promoted: list[str] = []
        self.gate = threading.Event()
        self.gate.set()

    def run_experiment(self, body: JsonObject) -> ExperimentOutcome:
        self.gate.wait(5)
        self.bodies.append(body)
        return ExperimentOutcome(f"exp{len(self.bodies)}", "finished")

    def score(self, experiment: str, score: JsonObject) -> None:
        self.scores.append((experiment, score))

    def promote(self, experiment: str) -> Promotion:
        self.promoted.append(experiment)
        return Promotion(2, None, (("sha2", "no PIAA"),))


class FakeData(DataPort):
    def json_page(self, page: int, per_page: int) -> IdPage:
        return IdPage(("j1",), 1)


class RecordingNotifier(Notifier):
    def __init__(self) -> None:
        self.sent: list[tuple[str, JsonObject]] = []

    def notify(self, actor: Actor, payload: JsonObject) -> str | None:
        self.sent.append((actor.name, payload))
        return None if actor.callback_url else "no url"


def _executor() -> tuple[Executor, MemoryStore, FakeChunking, RecordingNotifier]:
    store, chunking, notifier = MemoryStore(), FakeChunking(), RecordingNotifier()
    actors = ActorRegistry()
    actors.put(Actor("lab", "http://lab.local/hook"))
    executor = Executor(store, Modules(FakeIngesta(), chunking, FakeData()), notifier, actors, lambda r: f"/a/{r.id}")
    return executor, store, chunking, notifier


def _settle(executor: Executor, store: MemoryStore, id: str) -> PipelineRun:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        run = store.run(id)
        if run is not None and executor.status(run) not in (RunStatus.RUNNING, RunStatus.QUEUED):
            return run
        time.sleep(0.01)
    raise AssertionError(f"the run {id} didn't settle")


def _launch(executor: Executor, files: Selection) -> PipelineRun:
    request = RunRequest("piaa", "prueba", files, {"conversion": {"conversion": {"heading_level": 1}}})
    return executor.launch(Engine.new("r1", request, PIAA, now()))


def test_the_piaa_template_end_to_end() -> None:
    executor, store, chunking, notifier = _executor()
    run = _launch(executor, Selection(pages=None, all=True, per_page=3))
    assert store.created == ["r1"] and "piaa" in store.saved_templates  # the built-in stored when first used
    run = _settle(executor, store, run.id)
    assert run.status == RunStatus.WAITING and run.waiting is not None and run.waiting.actor == "lab"
    assert chunking.bodies[0]["files"] == {"sha256s": [f"sha{i}" for i in range(7)]}
    assert chunking.bodies[0]["conversion"] == {"heading_level": 1}
    assert notifier.sent[-1][0] == "lab" and notifier.sent[-1][1]["experiment"] == "exp1"

    score: JsonObject = {"author": "lab", "criteria": {"coherencia": 3}}
    executor.decide("r1", "conversion", Decision(DecisionKind.RETRY, "lab", None, {"conversion": {"x": 2}}, score))
    run = _settle(executor, store, "r1")
    assert chunking.scores == [("exp1", score)]
    assert chunking.bodies[1]["conversion"] == {"heading_level": 1, "x": 2}
    assert chunking.bodies[1]["files"] == chunking.bodies[0]["files"]  # the same batch every iteration

    executor.decide("r1", "conversion", Decision(DecisionKind.APPROVE))
    run = _settle(executor, store, "r1")
    assert chunking.promoted == ["exp2"]
    assert run.artifacts["json_oficial"] == ["sha0", "sha1", "sha3", "sha4", "sha5", "sha6"]
    assert run.waiting is not None and run.waiting.actor == "lab2"
    assert chunking.bodies[2]["files"] == {"from_json": {"sha256s": ["sha0", "sha1", "sha3", "sha4", "sha5", "sha6"]}}
    assert run.events[-1].kind == "notify_failed"  # lab2 has no callback_url: recorded, still in the inbox

    executor.decide("r1", "chunking", Decision(DecisionKind.APPROVE))
    run = _settle(executor, store, "r1")
    assert run.waiting is not None and run.waiting.step == "embeber"
    executor.complete("r1", "embeber", Completion("embeber", {"engine": "local"}))
    run = _settle(executor, store, "r1")
    executor.complete("r1", "revisar", Completion("modelscenter", "ok"))
    run = _settle(executor, store, "r1")
    assert run.status == RunStatus.DONE
    assert [r.stage for r in run.records if r.status == "done"][:2] == ["seleccionar", "convertir"]


def test_pages_from_to_and_a_failed_selection() -> None:
    executor, store, _, _ = _executor()
    run = _launch(executor, Selection(sha256s=("nope",)))
    run = _settle(executor, store, run.id)
    assert run.status == RunStatus.FAILED and run.error is not None and "nope" in run.error


def test_cancel_while_a_task_runs_drops_its_result_and_resume_is_refused() -> None:
    executor, store, chunking, _ = _executor()
    chunking.gate.clear()
    run = _launch(executor, Selection(all=True))
    deadline = time.monotonic() + 5
    while not store.saved_runs["r1"].records and time.monotonic() < deadline:  # the selection is done
        time.sleep(0.01)
    with pytest.raises(ConflictError, match="running"):
        executor.resume("r1")
    executor.cancel("r1")
    chunking.gate.set()
    run = _settle(executor, store, run.id)
    time.sleep(0.05)
    run = store.saved_runs["r1"]
    assert run.status == RunStatus.CANCELLED and not any(r.stage == "convertir" for r in run.records)


def test_an_interrupted_run_resumes() -> None:
    executor, store, _, _ = _executor()
    request = RunRequest("piaa", "", Selection(all=True), {})
    stopped = Engine.start(Engine.new("r2", request, PIAA, now()), now())
    store.save_run(stopped, created=True)  # stored running, but this executor never ran it
    assert executor.status(stopped) == RunStatus.INTERRUPTED
    executor.resume("r2")
    run = _settle(executor, store, "r2")
    assert run.status == RunStatus.WAITING
