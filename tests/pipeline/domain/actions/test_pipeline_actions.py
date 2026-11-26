"""The catalog of actions (feature 044), each over fake ports: what it asks of its module (only ids) and what it
leaves for the next stage."""

from dataclasses import dataclass, field

import pytest
from pipeline_fakes import OlderChunking, OlderData, OlderEmbeddings

from pipeline.domain import CATALOG
from pipeline.models import (
    APPROVED_CHUNKING,
    APPROVED_EMBEDDINGS,
    APPROVED_LLM,
    CHUNKED,
    CHUNKING_APPLIED,
    CHUNKING_EXPERIMENT,
    EMBEDDED,
    EMBEDDINGS_EXPERIMENT,
    FILE_BATCH,
    LLM_APPLIED,
    PARSED,
    RAW_FILES,
    ActionContext,
    ActionError,
    ActionOutput,
    EmbeddingModel,
    IdPage,
    IngestaPort,
    JobOutcome,
    JobWatch,
    JsonObject,
    LlmModel,
    LlmPort,
    Modules,
    ParsingPort,
    PipelineRun,
    RunStatus,
    RunStore,
    Selection,
    SourcePage,
    Stage,
    Template,
)

MODEL = EmbeddingModel("m", default_tokens=128, max_tokens=512, default=True)


class Ingesta(IngestaPort):
    def __init__(self) -> None:
        self.ingestions = 0
        self.status = "terminada"

    def page(self, selection: Selection, page: int, per_page: int) -> SourcePage:
        return SourcePage(("a", "b"), 1, "r")

    def has(self, sha256: str) -> bool:
        return sha256 in ("a", "b")

    def ingest(self, watch: JobWatch | None = None) -> JobOutcome:
        self.ingestions += 1
        return JobOutcome(f"i{self.ingestions}", self.status, None, (), self.status == "terminada")


class Parsing(ParsingPort):
    def __init__(self) -> None:
        self.parsed: list[list[str]] = []

    def parse(self, sha256s: list[str], watch: JobWatch | None = None) -> JobOutcome:
        self.parsed.append(sha256s)
        done = sha256s or ["x", "y", "z"]  # none: every RAW still to parse
        return JobOutcome("p1", "done", None, tuple(s for s in done if s != "bad"), True)


class Chunking(OlderChunking):
    def __init__(self) -> None:
        self.bodies: list[JsonObject] = []
        self.applied: list[str] = []
        self.promoted: list[list[str]] = []
        self.status = "finished"

    def experiment(self, body: JsonObject, watch: JobWatch | None = None) -> JobOutcome:
        self.bodies.append(body)
        sha256s = body.get("sha256s")
        done = tuple(str(s) for s in sha256s) if isinstance(sha256s, list) else ()
        return JobOutcome(
            "c1", self.status, "boom" if self.status != "finished" else None, done, self.status == "finished"
        )

    def apply(self, experiment: str) -> None:
        self.applied.append(experiment)

    def promote(self, sha256s: list[str], watch: JobWatch | None = None) -> JobOutcome:
        self.promoted.append(sha256s)
        return JobOutcome("pr1", "finished", None, tuple(sha256s), True)


class Embeddings(OlderEmbeddings):
    def __init__(self) -> None:
        self.bodies: list[JsonObject] = []
        self.embedded: list[list[str]] = []
        self.applied: list[str] = []

    def models(self) -> list[EmbeddingModel]:
        return [MODEL]

    def embed(self, sha256s: list[str], watch: JobWatch | None = None) -> JobOutcome:
        self.embedded.append(sha256s)
        return JobOutcome("v1", "finished", None, tuple(sha256s), True)

    def experiment(self, body: JsonObject, watch: JobWatch | None = None) -> JobOutcome:
        self.bodies.append(body)
        return JobOutcome("e1", "finished", None, (), True)

    def apply(self, experiment: str) -> None:
        self.applied.append(experiment)


class Data(OlderData):
    def json_page(self, page: int, per_page: int) -> IdPage:
        return IdPage(("j1", "j2"), 1)


class Llm(LlmPort):
    def __init__(self) -> None:
        self.applied: list[JsonObject] = []

    def models(self) -> list[LlmModel]:
        return [LlmModel("qwen", 8192, installed=True, default=True), LlmModel("grande", 32768)]

    def apply(self, config: JsonObject) -> None:
        self.applied.append(config)


class Store(RunStore):
    def templates(self) -> list[Template]:
        return []

    def template(self, id: str) -> Template | None:
        return None

    def save_template(self, template: Template) -> None: ...

    def delete_template(self, id: str) -> bool:
        return False

    def runs(self) -> list[PipelineRun]:
        return []

    def run(self, id: str) -> PipelineRun | None:
        return None

    def save_run(self, run: PipelineRun, created: bool = False) -> None: ...


@dataclass
class Fakes:
    ingesta: Ingesta = field(default_factory=Ingesta)
    parsing: Parsing = field(default_factory=Parsing)
    chunking: Chunking = field(default_factory=Chunking)
    embeddings: Embeddings = field(default_factory=Embeddings)
    data: Data = field(default_factory=Data)
    llm: Llm = field(default_factory=Llm)

    def run(self, action: str, artifacts: JsonObject | None = None, config: JsonObject | None = None) -> ActionOutput:
        stage = Stage("s", action)
        run = PipelineRun(
            "r1", "prueba", Template("t", "t", "", (stage,)), RunStatus.RUNNING, "now", Selection(all=True)
        )
        modules = Modules(self.ingesta, self.parsing, self.chunking, self.embeddings, self.data, self.llm)
        context = ActionContext(run, stage, config or {}, artifacts or {}, modules, Store(), 1)
        return CATALOG[action].run(context)


@pytest.fixture
def fakes() -> Fakes:
    return Fakes()


def test_the_ingestion_leaves_its_id_and_a_failed_one_fails_the_stage(fakes: Fakes) -> None:
    assert fakes.run("ingesta.run").artifacts == {RAW_FILES: "i1"}
    fakes.ingesta.status = "fallida"
    with pytest.raises(ActionError, match="ingestion i2 ended fallida"):
        fakes.run("ingesta.run")


def test_the_selection_freezes_the_batch(fakes: Fakes) -> None:
    assert fakes.run("ingesta.chunkable").artifacts == {FILE_BATCH: ["a", "b"]}
    with pytest.raises(ActionError, match="'c'"):
        fakes.run("ingesta.chunkable", config={"files": {"sha256s": ["a", "c"]}})


def test_parse_all_asks_parsing_for_everything_still_to_parse(fakes: Fakes) -> None:
    output = fakes.run("parsing.parse_all", {RAW_FILES: "i1"})
    assert output.artifacts == {PARSED: ["x", "y", "z"]} and fakes.parsing.parsed == [[]]


def test_parse_gives_the_parsed_ones_of_the_batch(fakes: Fakes) -> None:
    output = fakes.run("parsing.parse", {FILE_BATCH: ["a", "bad"]}, {"ingest_missing": False})
    assert output.artifacts == {PARSED: ["a"]} and fakes.parsing.parsed == [["a", "bad"]]
    assert isinstance(output.result, dict) and output.result["failed"] == ["bad"]


def test_parse_ingests_and_retries_the_ones_it_couldnt_parse(fakes: Fakes) -> None:
    output = fakes.run("parsing.parse", {FILE_BATCH: ["a", "bad"]})
    assert fakes.ingesta.ingestions == 1 and fakes.parsing.parsed == [["a", "bad"], ["bad"]]
    assert output.artifacts == {PARSED: ["a"]}


def test_parse_fails_when_nothing_of_the_batch_is_parsed(fakes: Fakes) -> None:
    with pytest.raises(ActionError, match="none of the batch"):
        fakes.run("parsing.parse", {FILE_BATCH: ["bad"]}, {"ingest_missing": False})


def test_the_chunking_experiment_gets_the_batch_and_the_fitted_pair(fakes: Fakes) -> None:
    config: JsonObject = {"chunking": {"chunker": "hybrid"}, "embeddings": {}}
    output = fakes.run("chunking.experiment", {PARSED: ["a", "b"]}, config)
    body = fakes.chunking.bodies[0]
    assert body["sha256s"] == ["a", "b"]
    assert body["chunking"] == {"chunker": "hybrid", "tokenizer": "m", "max_tokens": 126}
    assert output.artifacts == {CHUNKING_EXPERIMENT: "c1"} and output.experiment == "c1"


def test_a_pair_that_doesnt_fit_fails_before_chunking(fakes: Fakes) -> None:
    with pytest.raises(ActionError, match="can't pass 510"):
        fakes.run("chunking.experiment", {PARSED: ["a"]}, {"chunking": {"max_tokens": 511}})
    assert fakes.chunking.bodies == []


def test_a_failed_chunking_experiment_fails_the_stage(fakes: Fakes) -> None:
    fakes.chunking.status = "failed"
    with pytest.raises(ActionError, match="c1 ended failed: boom"):
        fakes.run("chunking.experiment", {PARSED: ["a"]})


def test_the_embeddings_experiment_gets_max_tokens_plus_the_special_tokens(fakes: Fakes) -> None:
    config: JsonObject = {"chunking": {"max_tokens": 100}, "embeddings": {"model": "m"}}
    output = fakes.run("embeddings.experiment", {CHUNKING_EXPERIMENT: "c1"}, config)
    body = fakes.embeddings.bodies[0]
    assert (body["chunking_experiment"], body["model"], body["max_tokens"]) == ("c1", "m", 102)
    assert output.artifacts == {EMBEDDINGS_EXPERIMENT: "e1"} and output.embeddings_experiment == "e1"


def test_applying_passes_the_approved_experiments(fakes: Fakes) -> None:
    assert fakes.run("chunking.apply", {APPROVED_CHUNKING: "c2"}).artifacts == {CHUNKING_APPLIED: "c2"}
    fakes.run("embeddings.apply", {APPROVED_EMBEDDINGS: "e2"})
    assert (fakes.chunking.applied, fakes.embeddings.applied) == (["c2"], ["e2"])


@pytest.mark.parametrize(("scope", "asked"), [("new", ["a"]), ("all", ["j1", "j2"])])
def test_promote_chunks_the_just_parsed_or_every_parsed_one(fakes: Fakes, scope: str, asked: list[str]) -> None:
    output = fakes.run("chunking.promote", {PARSED: ["a"]}, {"scope": scope})
    assert fakes.chunking.promoted == [asked] and output.artifacts == {CHUNKED: asked}


def test_with_nothing_parsed_promote_and_embed_launch_nothing(fakes: Fakes) -> None:
    assert fakes.run("chunking.promote", {PARSED: []}).artifacts == {CHUNKED: []}
    assert fakes.run("embeddings.embed", {CHUNKED: []}).artifacts == {EMBEDDED: []}
    assert fakes.chunking.promoted == [] and fakes.embeddings.embedded == []


def test_embed_gets_the_chunked_documents(fakes: Fakes) -> None:
    assert fakes.run("embeddings.embed", {CHUNKED: ["a", "b"]}).artifacts == {EMBEDDED: ["a", "b"]}
    assert fakes.embeddings.embedded == [["a", "b"]]


def test_an_unknown_scope_fails_the_stage(fakes: Fakes) -> None:
    with pytest.raises(ActionError, match="scope"):
        fakes.run("chunking.promote", {PARSED: ["a"]}, {"scope": "some"})


def test_llm_apply_puts_the_approved_iterations_llm(fakes: Fakes) -> None:
    llm: JsonObject = {"model": "qwen", "temperature": 0.1}
    output = fakes.run("llm.apply", {APPROVED_EMBEDDINGS: "e1", APPROVED_LLM: llm})
    assert fakes.llm.applied == [llm] and output.artifacts == {LLM_APPLIED: llm}


def test_llm_apply_skips_a_cycle_without_llm(fakes: Fakes) -> None:
    output = fakes.run("llm.apply", {APPROVED_EMBEDDINGS: "e1"})
    assert fakes.llm.applied == [] and output.artifacts == {LLM_APPLIED: None}
