"""Executor (features 028 and 044): `laboratorio` and `produccion` end to end with fake ports (no server): the module
queues, the waits, the answers, the pair checked before anything runs, the notifications and cancel/resume."""

import threading
import time

import pytest
from fastapi import Response
from pipeline_fakes import OlderChunking, OlderData, OlderEmbeddings

from common.clock import now
from pipeline.api.actor_registry import ActorRegistry
from pipeline.api.executor import Executor
from pipeline.api.routes.runs import start_run
from pipeline.api.schemas import NewRun
from pipeline.domain import LABORATORY, PRODUCTION, Engine, scoped
from pipeline.models import (
    Actor,
    ConflictError,
    Decision,
    DecisionKind,
    EmbeddingModel,
    IdPage,
    IngestaPort,
    InvalidRequest,
    JobOutcome,
    JobWatch,
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
        self.ingestions = 0

    def page(self, selection: Selection, page: int, per_page: int) -> SourcePage:
        pages = -(-len(self.files) // per_page)
        return SourcePage(tuple(self.files[(page - 1) * per_page : page * per_page]), pages, "2026-10-01")

    def has(self, sha256: str) -> bool:
        return sha256 in self.files

    def ingest(self, watch: JobWatch | None = None) -> JobOutcome:
        self.ingestions += 1
        return JobOutcome(f"i{self.ingestions}", "terminada", succeeded=True)


class FakeParsing(ParsingPort):
    def __init__(self) -> None:
        self.parsed = {"sha0", "sha1"}
        self.asked: list[list[str]] = []

    def parse(self, sha256s: list[str], watch: JobWatch | None = None) -> JobOutcome:
        self.asked.append(sha256s)
        done = sha256s or ["new1", "new2"]  # none: every RAW still to parse, as parsing decides
        self.parsed |= set(done)
        return JobOutcome("p1", "done", None, tuple(done), True)


class FakeChunking(OlderChunking):
    def __init__(self) -> None:
        self.bodies: list[JsonObject] = []
        self.applied: list[str] = []
        self.promoted: list[list[str]] = []
        self.gate = threading.Event()
        self.gate.set()

    def experiment(self, body: JsonObject, watch: JobWatch | None = None) -> JobOutcome:
        self.gate.wait(5)
        self.bodies.append(body)
        return JobOutcome(f"c{len(self.bodies)}", "finished", succeeded=True)

    def apply(self, experiment: str) -> None:
        self.applied.append(experiment)

    def promote(self, sha256s: list[str], watch: JobWatch | None = None) -> JobOutcome:
        self.promoted.append(sha256s)
        return JobOutcome("pr1", "finished", None, tuple(sha256s), True)


class FakeEmbeddings(OlderEmbeddings):
    def __init__(self) -> None:
        self.bodies: list[JsonObject] = []
        self.applied: list[str] = []
        self.embedded: list[list[str]] = []

    def models(self) -> list[EmbeddingModel]:
        return [EmbeddingModel("m", 128, 512, True)]

    def embed(self, sha256s: list[str], watch: JobWatch | None = None) -> JobOutcome:
        self.embedded.append(sha256s)
        return JobOutcome("v1", "finished", None, tuple(sha256s), True)

    def experiment(self, body: JsonObject, watch: JobWatch | None = None) -> JobOutcome:
        self.bodies.append(body)
        return JobOutcome(f"e{len(self.bodies)}", "finished", succeeded=True)

    def apply(self, experiment: str) -> None:
        self.applied.append(experiment)


class FakeData(OlderData):
    def json_page(self, page: int, per_page: int) -> IdPage:
        return IdPage(("sha0", "new1", "new2"), 1)


class FakeLlm(LlmPort):
    def __init__(self) -> None:
        self.applied: list[JsonObject] = []

    def models(self) -> list[LlmModel]:
        return [LlmModel("qwen", 8192, installed=True, default=True), LlmModel("grande", 32768)]

    def apply(self, config: JsonObject) -> None:
        self.applied.append(config)


class RecordingNotifier(Notifier):
    def __init__(self) -> None:
        self.sent: list[tuple[str, JsonObject]] = []

    def notify(self, actor: Actor, payload: JsonObject) -> str | None:
        self.sent.append((actor.name, payload))
        return None if actor.callback_url else "no url"


class Setup:
    def __init__(self) -> None:
        self.store, self.notifier = MemoryStore(), RecordingNotifier()
        self.ingesta, self.parsing, self.chunking = FakeIngesta(), FakeParsing(), FakeChunking()
        self.embeddings, self.llm = FakeEmbeddings(), FakeLlm()
        actors = ActorRegistry()
        actors.put(Actor("lab", "http://lab.local/hook"))
        modules = Modules(self.ingesta, self.parsing, self.chunking, self.embeddings, FakeData(), self.llm)
        self.executor = Executor(self.store, modules, self.notifier, actors, lambda r: f"/a/{r.id}")

    def settle(self, id: str) -> PipelineRun:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            run = self.store.run(id)
            if run is not None and self.executor.status(run) not in (RunStatus.RUNNING, RunStatus.QUEUED):
                return run
            time.sleep(0.01)
        raise AssertionError(f"the run {id} didn't settle")

    def lab(self, files: Selection, params: dict[str, JsonObject] | None = None) -> PipelineRun:
        request = RunRequest("laboratorio", "prueba", files, params or {})
        return self.executor.launch(Engine.new("r1", request, LABORATORY, now()))


@pytest.fixture
def setup() -> Setup:
    return Setup()


@pytest.mark.integration
def test_the_laboratory_end_to_end(setup: Setup) -> None:
    run = setup.settle(setup.lab(Selection(all=True, per_page=3)).id)
    assert setup.store.created == ["r1"] and "laboratorio" in setup.store.saved_templates
    assert run.status == RunStatus.WAITING and run.waiting is not None and run.waiting.actor == "lab"
    batch = [f"sha{i}" for i in range(7)]
    assert setup.parsing.asked == [batch]  # the whole batch: parsing skips what is already parsed
    assert setup.chunking.bodies[0]["sha256s"] == batch  # the already parsed and the just parsed
    assert setup.chunking.bodies[0]["chunking"] == {"chunker": "hybrid", "tokenizer": "m", "max_tokens": 126}
    embeddings = setup.embeddings.bodies[0]
    assert (embeddings["chunking_experiment"], embeddings["model"], embeddings["max_tokens"]) == ("c1", "m", 128)
    assert setup.notifier.sent[-1][1]["experiment"] == "c1"
    assert setup.notifier.sent[-1][1]["embeddings_experiment"] == "e1"

    score: JsonObject = {"score": 3, "author": "lab", "criteria": {"coherencia": 3}}
    retry = Decision(DecisionKind.RETRY, "lab", None, {"chunking": {"max_tokens": 64}}, score)
    setup.executor.decide("r1", "laboratorio", retry)
    run = setup.settle("r1")
    assert run.iterations[0].score == score  # the pair's score stays on the iteration
    assert setup.chunking.bodies[1]["sha256s"] == batch  # the same batch every iteration
    second = setup.chunking.bodies[1]["chunking"]
    assert isinstance(second, dict) and second["max_tokens"] == 64
    assert setup.embeddings.bodies[1]["max_tokens"] == 66

    setup.executor.decide("r1", "laboratorio", Decision(DecisionKind.APPROVE))
    run = setup.settle("r1")
    assert run.status == RunStatus.DONE
    assert (setup.chunking.applied, setup.embeddings.applied) == (["c2"], ["e2"])


def test_a_retry_whose_pair_doesnt_fit_is_refused_and_changes_nothing(setup: Setup) -> None:
    setup.settle(setup.lab(Selection(all=True)).id)
    before = setup.store.run("r1")
    with pytest.raises(InvalidRequest, match="can't pass 510"):
        setup.executor.decide("r1", "laboratorio", Decision(DecisionKind.RETRY, next={"chunking": {"max_tokens": 600}}))
    assert setup.store.run("r1") == before and len(setup.chunking.bodies) == 1


def test_a_laboratory_whose_first_pair_doesnt_fit_never_starts(setup: Setup) -> None:
    with pytest.raises(InvalidRequest, match="isn't admitted"):
        setup.lab(Selection(all=True), {"laboratorio": {"embeddings": {"model": "otro"}}})
    assert setup.store.saved_runs == {} and setup.chunking.bodies == []


@pytest.mark.integration
@pytest.mark.parametrize(("scope", "chunked"), [("new", ["new1", "new2"]), ("all", ["sha0", "new1", "new2"])])
def test_production_end_to_end(setup: Setup, scope: str, chunked: list[str]) -> None:
    params = scoped(PRODUCTION.stages, {}, scope)
    run = setup.executor.launch(Engine.new("r2", RunRequest("produccion", "", None, params), PRODUCTION, now()))
    run = setup.settle(run.id)
    assert run.status == RunStatus.DONE and setup.ingesta.ingestions == 1
    assert setup.parsing.asked == [[]]  # production lets parsing take everything still to parse
    assert setup.chunking.promoted == [chunked] and setup.embeddings.embedded == [chunked]


def test_a_selection_of_unknown_files_fails(setup: Setup) -> None:
    run = setup.settle(setup.lab(Selection(sha256s=("nope",))).id)
    assert run.status == RunStatus.FAILED and run.error is not None and "nope" in run.error


def test_cancel_while_a_task_runs_drops_its_result_and_resume_is_refused(setup: Setup) -> None:
    setup.chunking.gate.clear()
    run = setup.lab(Selection(all=True))
    deadline = time.monotonic() + 5
    while len(setup.store.saved_runs["r1"].records) < 2 and time.monotonic() < deadline:  # selected, parsed
        time.sleep(0.01)
    with pytest.raises(ConflictError, match="running"):
        setup.executor.resume("r1")
    setup.executor.cancel("r1")
    setup.chunking.gate.set()
    setup.settle(run.id)
    time.sleep(0.05)
    run = setup.store.saved_runs["r1"]
    assert run.status == RunStatus.CANCELLED and not any(r.stage == "chunkear" for r in run.records)


def test_an_interrupted_run_resumes(setup: Setup) -> None:
    request = RunRequest("laboratorio", "", Selection(all=True), {})
    stopped = Engine.start(Engine.new("r2", request, LABORATORY, now()), now())
    setup.store.save_run(stopped, created=True)  # stored running, but this executor never ran it
    assert setup.executor.status(stopped) == RunStatus.INTERRUPTED
    setup.executor.resume("r2")
    assert setup.settle("r2").status == RunStatus.WAITING


def test_a_laboratory_without_llm_never_asks_llm(setup: Setup) -> None:
    setup.settle(setup.lab(Selection(all=True)).id)
    assert setup.notifier.sent[-1][1]["llm"] is None
    setup.executor.decide("r1", "laboratorio", Decision(DecisionKind.APPROVE))
    run = setup.settle("r1")
    assert run.status == RunStatus.DONE and setup.llm.applied == []


def test_a_laboratory_whose_llm_isnt_downloaded_never_starts(setup: Setup) -> None:
    with pytest.raises(InvalidRequest, match="isn't downloaded"):
        setup.lab(Selection(all=True), {"laboratorio": {"llm": {"model": "grande"}}})
    assert setup.store.saved_runs == {} and setup.chunking.bodies == []


@pytest.mark.integration
def test_the_trio_retries_only_the_llm_and_applies_it(setup: Setup) -> None:
    llm: JsonObject = {"model": "qwen", "temperature": 0.2}
    setup.settle(setup.lab(Selection(all=True), {"laboratorio": {"llm": llm}}).id)
    assert setup.notifier.sent[-1][1]["llm"] == llm  # lab asks /consultas/ask with it

    with pytest.raises(InvalidRequest, match="isn't admitted"):  # a retry whose llm can't be used changes nothing
        setup.executor.decide("r1", "laboratorio", Decision(DecisionKind.RETRY, next={"llm": {"model": "nope"}}))
    setup.executor.decide("r1", "laboratorio", Decision(DecisionKind.RETRY, next={"llm": {"temperature": 0.8}}))
    run = setup.settle("r1")
    assert run.status == RunStatus.WAITING and run.waiting is not None and run.waiting.iteration == 2
    assert (len(setup.chunking.bodies), len(setup.embeddings.bodies)) == (1, 1)  # the experiments are reused
    payload = setup.notifier.sent[-1][1]
    assert payload["llm"] == {"model": "qwen", "temperature": 0.8} and payload["embeddings_experiment"] == "e1"

    setup.executor.decide("r1", "laboratorio", Decision(DecisionKind.APPROVE))
    run = setup.settle("r1")
    assert run.status == RunStatus.DONE
    assert (setup.chunking.applied, setup.embeddings.applied) == (["c1"], ["e1"])
    assert setup.llm.applied == [{"model": "qwen", "temperature": 0.8}]


def _production(setup: Setup, files: Selection | None, part_size: int | None = None) -> PipelineRun:
    request = RunRequest("produccion", "", files, {}, part_size)
    return setup.executor.launch(Engine.new("r3", request, PRODUCTION, now()))


def test_production_with_files_processes_only_the_batch(setup: Setup) -> None:
    run = setup.settle(_production(setup, Selection(sha256s=("sha2", "sha3"))).id)
    assert run.status == RunStatus.DONE and setup.ingesta.ingestions == 1
    assert setup.parsing.asked == [["sha2", "sha3"]]  # never [] (everything missing)
    assert setup.chunking.promoted == [["sha2", "sha3"]] and setup.embeddings.embedded == [["sha2", "sha3"]]


@pytest.mark.integration
def test_production_by_parts_goes_part_after_part_through_every_stage(setup: Setup) -> None:
    run = setup.settle(_production(setup, None, part_size=3).id)  # without files: every chunkable file
    assert run.status == RunStatus.DONE and [len(p.sha256s) for p in run.parts] == [3, 3, 1]
    assert setup.parsing.asked == [["sha0", "sha1", "sha2"], ["sha3", "sha4", "sha5"], ["sha6"]]
    assert setup.chunking.promoted == setup.parsing.asked and setup.embeddings.embedded == setup.parsing.asked
    stages = [(r.stage, r.part) for r in run.records]
    assert stages[:5] == [("ingestar", None), ("partes", None), ("parsear", 1), ("chunkear", 1), ("embeber", 1)]


class StoppableParsing(FakeParsing):
    """A parsing run that only ends when it is asked to stop (feature 056)."""

    def __init__(self) -> None:
        super().__init__()
        self.running = threading.Event()
        self.stopped = threading.Event()

    def parse(self, sha256s: list[str], watch: JobWatch | None = None) -> JobOutcome:
        self.asked.append(sha256s)
        assert watch is not None
        watch.started(self.stopped.set)
        self.running.set()
        self.stopped.wait(5)
        watch.ended()
        return JobOutcome("p1", "cancelled", None, tuple(sha256s[:1]), False)


def test_cancel_stops_the_running_job_and_launches_nothing_more(setup: Setup) -> None:
    parsing = StoppableParsing()
    modules = Modules(setup.ingesta, parsing, setup.chunking, setup.embeddings, FakeData(), setup.llm)
    executor = Executor(setup.store, modules, setup.notifier, ActorRegistry(), lambda r: "")
    request = RunRequest("produccion", "", None, {}, 2)
    executor.launch(Engine.new("r4", request, PRODUCTION, now()))
    assert parsing.running.wait(5)
    run = executor.cancel("r4")
    assert parsing.stopped.is_set() and run.status == RunStatus.CANCELLED
    time.sleep(0.05)
    run = setup.store.saved_runs["r4"]
    assert run.status == RunStatus.CANCELLED and run.parts[0].status.value == "cancelled"
    assert parsing.asked == [["sha0", "sha1"]] and setup.chunking.promoted == []


def test_simulating_production_by_parts_answers_the_batch_it_would_freeze(setup: Setup) -> None:
    new = NewRun(template="produccion", files={"sha256s": ["sha2", "sha3"]}, part_size=1, simulate=True)
    started = start_run(setup.store, setup.executor, new, Response())
    assert (started.status, started.batch) == ("simulated", ["sha2", "sha3"])
    assert setup.store.saved_runs == {} and setup.parsing.asked == []
