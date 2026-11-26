"""targets (feature 060): the official models worth asking and the finished embeddings experiments, with fake ports."""

from dataclasses import dataclass, field

from consultas.domain import targets
from consultas.models import (
    ChunkingExperiment,
    ChunkingParameters,
    Coverage,
    EmbeddingModel,
    EmbeddingsRun,
    ExperimentTarget,
    OfficialTarget,
)

MINI, E5, BGE = (
    EmbeddingModel("mini", 384, "embedding_mini_384"),
    EmbeddingModel("e5", 768, "embedding_e5_768"),
    EmbeddingModel("bge", 1024, "embedding_bge_1024"),
)


@dataclass
class FakeCatalog:
    served: list[EmbeddingModel] = field(default_factory=lambda: [MINI, E5, BGE])
    active: str = "mini"
    runs: list[EmbeddingsRun] = field(default_factory=list)

    def models(self) -> list[EmbeddingModel]:
        return self.served

    def active_model(self) -> str:
        return self.active

    def experiments(self) -> list[EmbeddingsRun]:
        return self.runs


@dataclass
class FakeProgress:
    done: dict[str, int] = field(default_factory=dict)

    def coverage(self, vector_property: str) -> Coverage:
        return Coverage(self.done.get(vector_property, 0), 100)


@dataclass
class FakeChunking:
    known: dict[str, ChunkingExperiment] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)

    def experiment(self, id: str) -> ChunkingExperiment | None:
        self.asked.append(id)
        return self.known.get(id)


def run(id: str, status: str = "finished", chunking: str | None = "c1", dimensions: int | None = None) -> EmbeddingsRun:
    return EmbeddingsRun(id, f"exp {id}", status, "e5", dimensions, chunking, 12)


def test_the_official_targets_are_the_models_with_vectors_and_the_active_one() -> None:
    found = targets(FakeCatalog(active="bge"), FakeProgress({"embedding_e5_768": 40}), FakeChunking()).official
    assert found == [OfficialTarget("e5", 768, False, 40, 100), OfficialTarget("bge", 1024, True, 0, 100)]


def test_only_finished_experiments_are_targets_with_their_chunking() -> None:
    chunking = FakeChunking({"c1": ChunkingExperiment("c1", "hybrid 510", "hybrid", "e5", 510)})
    catalog = FakeCatalog(runs=[run("x1"), run("x2", status="running")])
    [found] = targets(catalog, FakeProgress(), chunking).experiments
    assert found == ExperimentTarget(
        "x1", "exp x1", "e5", 768, "c1", "hybrid 510", ChunkingParameters("hybrid", "e5", 510), 12
    )


def test_each_chunking_experiment_is_asked_once() -> None:
    chunking = FakeChunking({"c1": ChunkingExperiment("c1", "h", "hybrid", "e5", 510)})
    targets(FakeCatalog(runs=[run("x1"), run("x2"), run("x3", chunking=None)]), FakeProgress(), chunking)
    assert chunking.asked == ["c1"]


def test_a_deleted_chunking_experiment_leaves_its_data_empty() -> None:
    [found] = targets(FakeCatalog(runs=[run("x1")]), FakeProgress(), FakeChunking()).experiments
    assert (found.chunking_experiment, found.chunking_name, found.chunking) == ("c1", None, None)


def test_the_dimensions_embeddings_says_win_over_the_model() -> None:
    [found] = targets(FakeCatalog(runs=[run("x1", dimensions=7)]), FakeProgress(), FakeChunking()).experiments
    assert found.dimensions == 7
