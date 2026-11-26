"""Bases of the pipeline's fake ports (feature 062): the routes of the experiments pipeline, which most tests don't
use; a fake port that only needs the older ones subclasses these, and a call to a newer one fails the test."""

from dataclasses import dataclass, field

from pipeline.models import (
    AddedDocuments,
    ChunkingExperimentInfo,
    ChunkingPort,
    DataPort,
    EmbeddingModel,
    EmbeddingsExperimentInfo,
    EmbeddingsPort,
    ExperimentState,
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
    RunStore,
    SelectedPage,
    Selection,
    SourcePage,
    Template,
)

UNUSED = "the experiments pipeline isn't used by this test"


class OlderChunking(ChunkingPort):
    def start_experiment(self, body: JsonObject, watch: JobWatch | None = None) -> str:
        raise AssertionError(UNUSED)

    def experiment_info(self, experiment: str) -> ChunkingExperimentInfo | None:
        raise AssertionError(UNUSED)

    def add_documents(self, experiment: str, sha256s: list[str], watch: JobWatch | None = None) -> AddedDocuments:
        raise AssertionError(UNUSED)

    def resume_experiment(self, experiment: str, watch: JobWatch | None = None) -> None:
        raise AssertionError(UNUSED)

    def config(self) -> JsonObject | None:
        raise AssertionError(UNUSED)


class OlderEmbeddings(EmbeddingsPort):
    def experiments_of(self, chunking_experiment: str) -> list[EmbeddingsExperimentInfo]:
        raise AssertionError(UNUSED)

    def resume(self, experiment: str, watch: JobWatch | None = None) -> JobOutcome:
        raise AssertionError(UNUSED)

    def embed_model(self, sha256s: list[str], model: str, watch: JobWatch | None = None) -> JobOutcome:
        raise AssertionError(UNUSED)


MINILM = EmbeddingModel("minilm", 128, 512, True, 510, 126, 478)
E5 = EmbeddingModel("e5", 512, 512, False, 507, 507, 459)  # its `passage: ` prefix takes 3 tokens
BGE = EmbeddingModel("bge", 8192, 8192, False, 8190, 8190, 8142)


class ExperimentsChunking(ChunkingPort):
    """Chunking for the experiments pipeline: experiments by id with a status and their parameters."""

    def __init__(self) -> None:
        self.experiments: dict[str, ChunkingExperimentInfo] = {}
        self.started: list[JsonObject] = []
        self.added: list[tuple[str, list[str]]] = []
        self.resumed: list[str] = []
        self.active: JsonObject | None = {"chunker": "hybrid", "tokenizer": "minilm", "max_tokens": 126}

    def experiment(self, body: JsonObject, watch: JobWatch | None = None) -> JobOutcome:
        raise AssertionError("the experiments pipeline doesn't wait in chunking")

    def apply(self, experiment: str) -> None:
        raise AssertionError(UNUSED)

    def promote(self, sha256s: list[str], watch: JobWatch | None = None) -> JobOutcome:
        raise AssertionError(UNUSED)

    def start_experiment(self, body: JsonObject, watch: JobWatch | None = None) -> str:
        self.started.append(body)
        id = f"c{len(self.started)}"
        chunking = body.get("chunking")
        parameters = dict(chunking) if isinstance(chunking, dict) else {}
        self.experiments[id] = ChunkingExperimentInfo(id, "queued", parameters)
        return id

    def experiment_info(self, experiment: str) -> ChunkingExperimentInfo | None:
        return self.experiments.get(experiment)

    def add_documents(self, experiment: str, sha256s: list[str], watch: JobWatch | None = None) -> AddedDocuments:
        self.added.append((experiment, sha256s))
        return AddedDocuments(len(sha256s), 0, 0, 10 + len(sha256s))

    def resume_experiment(self, experiment: str, watch: JobWatch | None = None) -> None:
        self.resumed.append(experiment)

    def config(self) -> JsonObject | None:
        return self.active


class ExperimentsEmbeddings(EmbeddingsPort):
    def __init__(self) -> None:
        self.served = [MINILM, E5, BGE]
        self.existing: list[EmbeddingsExperimentInfo] = []
        self.created: list[JsonObject] = []
        self.resumed: list[str] = []
        self.runs: list[tuple[list[str], str]] = []
        self.failing: set[str] = set()  # models whose job ends failed

    def models(self) -> list[EmbeddingModel]:
        return self.served

    def embed(self, sha256s: list[str], watch: JobWatch | None = None) -> JobOutcome:
        raise AssertionError(UNUSED)

    def experiment(self, body: JsonObject, watch: JobWatch | None = None) -> JobOutcome:
        self.created.append(body)
        id, model = f"e{len(self.created)}", str(body["model"])
        self.existing.insert(0, EmbeddingsExperimentInfo(id, model, "finished", 0))
        status = "failed" if model in self.failing else "finished"
        return JobOutcome(id, status, "boom" if model in self.failing else None, (), status == "finished")

    def apply(self, experiment: str) -> None:
        raise AssertionError(UNUSED)

    def experiments_of(self, chunking_experiment: str) -> list[EmbeddingsExperimentInfo]:
        return list(self.existing)

    def resume(self, experiment: str, watch: JobWatch | None = None) -> JobOutcome:
        self.resumed.append(experiment)
        return JobOutcome(experiment, "finished", None, (), True)

    def embed_model(self, sha256s: list[str], model: str, watch: JobWatch | None = None) -> JobOutcome:
        self.runs.append((sha256s, model))
        failed = model in self.failing
        return JobOutcome(f"r{len(self.runs)}", "failed" if failed else "finished", None, tuple(sha256s), not failed)


class ExperimentsData(DataPort):
    """data with parsed documents p0..p4 (chunked: p0..p2); an experiment has `had` of them."""

    def __init__(self) -> None:
        self.parsed = [f"p{i}" for i in range(5)]
        self.chunked = self.parsed[:3]
        self.had: dict[str, set[str]] = {}
        self.asked: list[tuple[str, JsonObject, str | None, int]] = []
        self.states: dict[str, ExperimentState] = {}

    def json_page(self, page: int, per_page: int) -> IdPage:
        raise AssertionError(UNUSED)

    def select(
        self, universe: str, files: JsonObject, exclude_experiment: str | None, page: int, per_page: int
    ) -> SelectedPage:
        self.asked.append((universe, files, exclude_experiment, page))
        found = self.chunked if universe == "chunked" else self.parsed
        asked = files.get("sha256s")
        if isinstance(asked, list):
            found = [s for s in found if s in asked]
        found = [s for s in found if s not in self.had.get(exclude_experiment or "", set())]
        pages = max(1, -(-len(found) // per_page))
        return SelectedPage(len(found), tuple(found[(page - 1) * per_page : page * per_page]), pages)

    def wait_experiment(self, experiment: str, watch: JobWatch | None = None) -> ExperimentState:
        return self.states.get(experiment, ExperimentState(experiment, "finished"))


class OlderData(DataPort):
    def select(
        self, universe: str, files: JsonObject, exclude_experiment: str | None, page: int, per_page: int
    ) -> SelectedPage:
        raise AssertionError(UNUSED)

    def wait_experiment(self, experiment: str, watch: JobWatch | None = None) -> ExperimentState:
        raise AssertionError(UNUSED)


class NoIngesta(IngestaPort):
    def page(self, selection: Selection, page: int, per_page: int) -> SourcePage:
        raise AssertionError("the experiments pipeline doesn't ask ingesta")

    def has(self, sha256: str) -> bool:
        raise AssertionError("the experiments pipeline doesn't ask ingesta")

    def ingest(self, watch: JobWatch | None = None) -> JobOutcome:
        raise AssertionError("the experiments pipeline doesn't ask ingesta")


class NoParsing(ParsingPort):
    def parse(self, sha256s: list[str], watch: JobWatch | None = None) -> JobOutcome:
        raise AssertionError("the experiments pipeline doesn't parse")


class NoLlm(LlmPort):
    def models(self) -> list[LlmModel]:
        raise AssertionError("the experiments pipeline doesn't ask llm")

    def apply(self, config: JsonObject) -> None:
        raise AssertionError("the experiments pipeline doesn't ask llm")


@dataclass
class ExperimentsModules:
    chunking: ExperimentsChunking = field(default_factory=ExperimentsChunking)
    embeddings: ExperimentsEmbeddings = field(default_factory=ExperimentsEmbeddings)
    data: ExperimentsData = field(default_factory=ExperimentsData)

    @property
    def modules(self) -> Modules:
        return Modules(NoIngesta(), NoParsing(), self.chunking, self.embeddings, self.data, NoLlm())


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
