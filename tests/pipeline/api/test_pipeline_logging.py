"""What the runs of the pipeline leave in the logs, with their id."""

import logging
import time

import pytest

from common.clock import now
from pipeline.api.actor_registry import ActorRegistry
from pipeline.api.executor import Executor
from pipeline.domain import LABORATORY, Engine
from pipeline.models import (
    Actor,
    ChunkingPort,
    DataPort,
    EmbeddingModel,
    EmbeddingsPort,
    IdPage,
    IngestaPort,
    JobOutcome,
    JsonObject,
    LlmModel,
    LlmPort,
    Modules,
    Notifier,
    ParsingPort,
    PipelineRun,
    RunRequest,
    RunStatus,
    RunStore,
    Selection,
    SourcePage,
    Stage,
    Template,
    UnavailableError,
)

LOGGER = "pipeline.api"
ONE_TASK = Template("t", "t", "", (Stage("seleccionar", "ingesta.chunkable"),))


class Store(RunStore):
    def __init__(self) -> None:
        self.saved: dict[str, PipelineRun] = {}

    def templates(self) -> list[Template]:
        return []

    def template(self, id: str) -> Template | None:
        return ONE_TASK

    def save_template(self, template: Template) -> None:
        pass

    def delete_template(self, id: str) -> bool:
        return False

    def runs(self) -> list[PipelineRun]:
        return list(self.saved.values())

    def run(self, id: str) -> PipelineRun | None:
        return self.saved.get(id)

    def save_run(self, run: PipelineRun, created: bool = False) -> None:
        self.saved[run.id] = run


class Ingesta(IngestaPort):
    def __init__(self, down: bool = False) -> None:
        self.down = down

    def page(self, selection: Selection, page: int, per_page: int) -> SourcePage:
        if self.down:
            raise UnavailableError("ingesta is down")
        return SourcePage(("sha1",), 1, "2026-10-01")

    def has(self, sha256: str) -> bool:
        return True

    def ingest(self) -> JobOutcome:
        return JobOutcome("i1", "terminada", succeeded=True)


class Parsing(ParsingPort):
    def parse(self, sha256s: list[str]) -> JobOutcome:
        return JobOutcome("p1", "done", None, tuple(sha256s), True)


class Chunking(ChunkingPort):
    def experiment(self, body: JsonObject) -> JobOutcome:
        return JobOutcome("exp1", "finished", succeeded=True)

    def apply(self, experiment: str) -> None:
        pass

    def promote(self, sha256s: list[str]) -> JobOutcome:
        return JobOutcome("pr1", "finished", None, tuple(sha256s), True)


class Embeddings(EmbeddingsPort):
    def models(self) -> list[EmbeddingModel]:
        return [EmbeddingModel("m", 128, 512, True)]

    def embed(self, sha256s: list[str]) -> JobOutcome:
        return JobOutcome("v1", "finished", None, tuple(sha256s), True)

    def experiment(self, body: JsonObject) -> JobOutcome:
        return JobOutcome("e1", "finished", succeeded=True)

    def apply(self, experiment: str) -> None:
        pass


class Data(DataPort):
    def json_page(self, page: int, per_page: int) -> IdPage:
        return IdPage(("j1",), 1)


class Llm(LlmPort):
    def __init__(self) -> None:
        self.applied: list[JsonObject] = []

    def models(self) -> list[LlmModel]:
        return [LlmModel("qwen", 8192, installed=True, default=True), LlmModel("grande", 32768)]

    def apply(self, config: JsonObject) -> None:
        self.applied.append(config)


class Refused(Notifier):
    def notify(self, actor: Actor, payload: JsonObject) -> str | None:
        return "http://lab.local/hook: 500"


def _run(caplog: pytest.LogCaptureFixture, template: Template, ingesta: Ingesta | None = None) -> Executor:
    """Runs r1 until it stops moving."""
    store = Store()
    modules = Modules(ingesta or Ingesta(), Parsing(), Chunking(), Embeddings(), Data(), Llm())
    executor = Executor(store, modules, Refused(), ActorRegistry(), lambda r: f"/a/{r.id}")
    request = RunRequest(template.id, "prueba", Selection(pages=None, all=True, per_page=3), {})
    with caplog.at_level(logging.INFO, logger=LOGGER):
        run = executor.launch(Engine.new("r1", request, template, now()))
        for _ in range(500):
            current = store.run(run.id)
            if current is not None and executor.status(current) not in (RunStatus.RUNNING, RunStatus.QUEUED):
                return executor
            time.sleep(0.01)
    raise AssertionError("the run didn't settle")


def _lines(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == level]


def test_a_run_says_when_it_starts(caplog: pytest.LogCaptureFixture) -> None:
    _run(caplog, ONE_TASK)
    assert any("r1" in line and "started" in line for line in _lines(caplog, logging.INFO))


def test_a_run_says_when_it_ends(caplog: pytest.LogCaptureFixture) -> None:
    _run(caplog, ONE_TASK)
    assert any("r1" in line and "finished" in line for line in _lines(caplog, logging.INFO))


def test_a_failed_stage_is_an_error_with_its_reason(caplog: pytest.LogCaptureFixture) -> None:
    _run(caplog, ONE_TASK, Ingesta(down=True))
    assert any("r1" in line and "ingesta is down" in line for line in _lines(caplog, logging.ERROR))


def test_a_run_says_who_it_waits_for(caplog: pytest.LogCaptureFixture) -> None:
    _run(caplog, LABORATORY)
    assert any("r1" in line and "waiting" in line and "lab" in line for line in _lines(caplog, logging.INFO))


def test_a_refused_notification_says_to_whom_and_why(caplog: pytest.LogCaptureFixture) -> None:
    _run(caplog, LABORATORY)
    warning = _lines(caplog, logging.WARNING)[0]
    for part in ("r1", "lab", "500"):
        assert part in warning


def test_a_cancelled_run_says_so(caplog: pytest.LogCaptureFixture) -> None:
    executor = _run(caplog, LABORATORY)
    with caplog.at_level(logging.INFO, logger=LOGGER):
        executor.cancel("r1")
    assert any("r1" in line and "cancelled" in line for line in _lines(caplog, logging.INFO))
