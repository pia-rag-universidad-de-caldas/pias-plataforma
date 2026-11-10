"""ExperimentRunner and ExperimentGraph (features 043 and 045), with fake ports: what an experiment takes, what it
records apart from the official chunks, what stops it, and what a resume chunks again."""

from chunking.domain import ExperimentGraph, ExperimentRunner, Parameters
from chunking.models import (
    UNPARSED,
    Chunk,
    Chunker,
    ChunkerUnavailable,
    ChunkingError,
    ChunkingParameters,
    DocumentUse,
    ExperimentRecord,
    ExperimentRequest,
    GraphBatch,
    GraphLabel,
    GraphRelation,
    ParsedDocument,
    RequestedChunking,
    SinkError,
)

PARAMETERS = Parameters.resolve(RequestedChunking(), "2")
A, B, C = "a" * 64, "b" * 64, "c" * 64


class Store:
    """An ExperimentStore over dicts."""

    def __init__(self, *parsed: str, used: tuple[str, ...] = (), down_after: int | None = None) -> None:
        self.parsed = set(parsed)
        self.used = list(used)
        self.saved: list[GraphBatch] = []
        self._down_after = down_after

    def document(self, sha256: str) -> ParsedDocument | None:
        if self._down_after is not None and len(self.saved) >= self._down_after:
            raise SinkError("data is down")
        status = "parseado" if sha256 in self.parsed else "error"
        return ParsedDocument(sha256, status, "p", "stored" if sha256 in self.parsed else None)

    def save(self, batch: GraphBatch) -> None:
        self.saved.append(batch)

    def experiment(self, id: str) -> ExperimentRecord | None:
        return None

    def experiments(self) -> list[ExperimentRecord]:
        return []

    def documents(self, experiment_id: str) -> list[str]:
        return self.used

    def uses(self, experiment_id: str) -> list[DocumentUse]:
        return []

    def missing(self, fingerprint: str, page: int | None, per_page: int | None) -> list[str]:
        return []

    def delete(self, id: str) -> bool:
        return False

    def chunked_with(self) -> list[ChunkingParameters | None]:
        return []


class Chunks(Chunker):
    def __init__(self, fail: str | None = None, unavailable: bool = False) -> None:
        self._fail, self._unavailable = fail, unavailable

    def available(self) -> bool:
        return True

    def version(self) -> str | None:
        return "2"

    def chunk(self, content: str, parameters: ChunkingParameters) -> list[Chunk]:
        if self._unavailable:
            raise ChunkerUnavailable("no tokenizer")
        if self._fail:
            raise ChunkingError(self._fail)
        return [Chunk(0, "uno", "T\nuno", ["T"], [1], 3), Chunk(1, "dos", "T\ndos", ["T"], [2], 5)]


def request(*sha256s: str, from_experiment: str | None = None) -> ExperimentRequest:
    return ExperimentRequest("prueba", "", PARAMETERS, list(sha256s), from_experiment)


def test_resolve_takes_the_parsed_ones_once_and_sets_aside_the_others() -> None:
    resolution = ExperimentRunner.resolve(Store(A, B), request(B, C, A, B))
    assert (resolution.sha256s, resolution.unparsed) == ([B, A], [C])


def test_resolve_from_another_experiment_takes_its_documents() -> None:
    resolution = ExperimentRunner.resolve(Store(A, used=(A, C)), request(from_experiment="e0"))
    assert (resolution.sha256s, resolution.unparsed) == ([A], [C])


def test_a_document_is_recorded_with_its_sections_and_chunks_apart_from_the_official_ones() -> None:
    store = Store(A)
    outcome = ExperimentRunner.run(store, Chunks(), "e1", request(A), ExperimentRunner.resolve(store, request(A)))
    [batch] = store.saved
    use = next(link for link in batch.links if link.type is GraphRelation.EXP_USA)
    assert (use.target.label, use.target.id, use.properties["chunks"], use.properties["tokens"]) == (
        GraphLabel.JSON,
        A,
        2,
        8,
    )
    assert {n.key.label for n in batch.nodes} == {GraphLabel.EXP_SECCION, GraphLabel.EXP_CHUNK}
    assert batch.replace_from is None  # nothing official is touched
    assert (outcome.results.chunked, outcome.results.chunks, outcome.results.by_document[0].sha256) == (1, 2, A)


def test_a_document_that_fails_is_recorded_and_the_rest_goes_on() -> None:
    store = Store(A, B)
    resolution = ExperimentRunner.resolve(store, request(A, B, C))
    outcome = ExperimentRunner.run(store, Chunks(fail="bad"), "e1", request(A, B, C), resolution)
    assert outcome.error is None and outcome.progress.errors == 2
    assert [f.error for f in outcome.results.failures] == [UNPARSED, "bad", "bad"]
    assert all(link.properties["estado"] == "error" for b in store.saved for link in b.links)


def test_data_down_or_no_chunker_stops_it() -> None:
    store = Store(A, B, down_after=1)
    resolution = ExperimentRunner.resolve(Store(A, B), request(A, B))
    assert ExperimentRunner.run(store, Chunks(), "e1", request(A, B), resolution).error == "data is down"
    stopped = ExperimentRunner.run(Store(A), Chunks(unavailable=True), "e1", request(A), resolution)
    assert stopped.error == "no tokenizer"


def test_the_experiment_node_records_what_was_asked_and_how_it_ended() -> None:
    created = ExperimentGraph.experiment("e1", request(A, A), 1, "2026")
    properties = created.nodes[0].properties
    assert properties["estado"] == "queued" and '"max_tokens": 126' in str(properties["chunking"])
    assert properties["documentos"] == f'{{"from_experiment": null, "sha256s": ["{A}"]}}'


def test_an_experiment_with_a_failed_document_ends_partial() -> None:
    store = Store(A)
    outcome = ExperimentRunner.run(
        store, Chunks(fail="bad"), "e1", request(A), ExperimentRunner.resolve(store, request(A))
    )
    ended = ExperimentGraph.finish("e1", outcome.results, outcome.progress, outcome.error, "2026")
    assert ended.nodes[0].properties["estado"] == "partial"
    assert ExperimentGraph.status("down", 0).value == "failed" and ExperimentGraph.status(None, 0).value == "finished"


def test_a_resume_chunks_only_what_wasnt_chunked_and_counts_every_document() -> None:
    store = Store(A, B)
    uses = [DocumentUse(A, True, 2, [3, 5]), DocumentUse(B, False, 0, [])]
    resolution, kept = ExperimentRunner.pending(store, request(A, B, C), uses)
    assert (resolution.sha256s, resolution.unparsed, [u.sha256 for u in kept]) == ([B], [C], [A])
    outcome = ExperimentRunner.run(store, Chunks(), "e1", request(A, B, C), resolution, kept=kept)
    assert [b.links[0].target.id for b in store.saved] == [B]  # A isn't chunked again
    assert (outcome.progress.files, outcome.progress.done, outcome.progress.chunks) == (2, 2, 4)
    assert (outcome.results.documents, outcome.results.chunked, outcome.results.chunks) == (3, 2, 4)
    assert outcome.results.tokens is not None and outcome.results.tokens.max == 5
