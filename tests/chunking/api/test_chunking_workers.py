"""What runs in line (features 043 and 045): an experiment and a run, end to end over a fake data, and what they leave
in the logs (their id, never the text of a document)."""

import logging
import threading
from types import TracebackType
from typing import Self, cast

import pytest

from chunking.adapters import HttpSession
from chunking.api.experiments import ExperimentRegistry, LiveExperiment
from chunking.api.experiments import worker as experiments_worker
from chunking.api.runs import RunRegistry, launch
from chunking.api.work_queue import WorkQueue
from chunking.domain import ExperimentRunner, Parameters
from chunking.models import (
    Chunk,
    Chunker,
    ChunkingParameters,
    ChunkingRun,
    ExperimentRecord,
    ExperimentRequest,
    GraphBatch,
    GraphLabel,
    ParsedDocument,
    RequestedChunking,
    RunStatus,
)

A, B = "a" * 64, "b" * 64
SECRET = "texto del documento que nunca va a los logs"
PARAMETERS = Parameters.resolve(RequestedChunking(), "2")


class Data:
    """Every store of the session over one list of batches; A is parsed, B isn't."""

    def __init__(self) -> None:
        self.saved: list[GraphBatch] = []
        self.asked: tuple[str, int | None, int | None] | None = None  # what was asked to GET /progress/chunking

    def document(self, sha256: str) -> ParsedDocument | None:
        return ParsedDocument(sha256, "parseado", "p", "stored") if sha256 == A else None

    def save(self, batch: GraphBatch) -> None:
        self.saved.append(batch)

    def experiment(self, id: str) -> ExperimentRecord | None:
        return None

    def documents(self, experiment_id: str) -> list[str]:
        return []

    def missing(self, fingerprint: str, page: int | None, per_page: int | None) -> list[str]:
        self.asked = (fingerprint, page, per_page)
        return [A, B]


class Session:
    def __init__(self, data: Data) -> None:
        self.documents = self.experiments = self.runs = data

    def __enter__(self) -> Self:
        return self

    def __exit__(self, kind: type[BaseException] | None, error: BaseException | None, tb: TracebackType | None) -> None:
        pass


class Chunks(Chunker):
    def available(self) -> bool:
        return True

    def version(self) -> str | None:
        return "2"

    def chunk(self, content: str, parameters: ChunkingParameters) -> list[Chunk]:
        return [Chunk(0, SECRET, SECRET, [], [1], 9)]


def drained(queue: WorkQueue) -> None:
    done = threading.Event()
    queue.submit("end", done.set)
    assert done.wait(5)


def test_an_experiment_runs_records_and_ends(caplog: pytest.LogCaptureFixture) -> None:
    data, queue = Data(), WorkQueue()
    registry = ExperimentRegistry(queue)
    request = ExperimentRequest("x", "", PARAMETERS, [A, B])
    resolution = ExperimentRunner.resolve(cast(HttpSession, Session(data)).experiments, request)
    registry.add(LiveExperiment("e1", "x", (), "2026"))
    with caplog.at_level(logging.INFO, logger="chunking"):
        experiments_worker.launch(
            queue, registry, "e1", lambda: cast(HttpSession, Session(data)), Chunks(), request, resolution
        )
        drained(queue)
    end = data.saved[-1].nodes[0].properties
    assert end["estado"] == "finished" and registry.live() == []
    assert '"chunked": 1' in str(end["resultados"]) and '"unparsed": 1' in str(end["resultados"])
    assert "experiment e1 ended finished" in caplog.text and B in caplog.text and SECRET not in caplog.text


def test_a_run_runs_and_says_what_it_chunked(caplog: pytest.LogCaptureFixture) -> None:
    data, queue, registry = Data(), WorkQueue(), RunRegistry()
    run = ChunkingRun("r1", RunStatus.QUEUED, "2026", False, PARAMETERS, [A, B, A])
    registry.add(run)
    with caplog.at_level(logging.INFO, logger="chunking"):
        launch(queue, registry, run, lambda: cast(HttpSession, Session(data)), Chunks())
        drained(queue)
    ended = registry.get("r1")
    assert ended is not None and (ended.status, ended.chunked, ended.progress.unparsed) == (RunStatus.FINISHED, [A], 1)
    records = [b for b in data.saved if b.nodes and b.nodes[0].key.label is GraphLabel.CORRIDA_CHUNKING]
    assert [r.nodes[0].properties["estado"] for r in records] == ["queued", "running", "finished"]
    assert "run r1 ended finished" in caplog.text and SECRET not in caplog.text


def test_a_run_of_what_is_missing_takes_it_when_its_turn_comes() -> None:
    data, queue, registry = Data(), WorkQueue(), RunRegistry()
    run = ChunkingRun("r1", RunStatus.QUEUED, "2026", False, PARAMETERS, [], frozen=False, page=2, per_page=20)
    registry.add(run)
    launch(queue, registry, run, lambda: cast(HttpSession, Session(data)), Chunks())
    drained(queue)
    ended = registry.get("r1")
    assert data.asked == (PARAMETERS.fingerprint, 2, 20)
    assert ended is not None and ended.frozen and ended.sha256s == [A, B]
