"""ExperimentRunner and ExperimentGraph (features 043 and 045), with fake ports: what an experiment takes, what it
records apart from the official chunks, what stops it, and what a resume chunks again."""

from chunking.domain import ExperimentGraph, ExperimentRunner, Parameters, Resolution
from chunking.models import (
    UNPARSED,
    Chunk,
    Chunker,
    ChunkerUnavailable,
    ChunkingError,
    ChunkingParameters,
    DocumentUse,
    ExperimentDependents,
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

    def dependents(self, id: str) -> ExperimentDependents:
        return ExperimentDependents([], [])

    def missing(self, fingerprint: str, page: int | None, per_page: int | None) -> list[str]:
        return []

    def parsed_documents(self) -> list[str]:
        return sorted(self.parsed)

    def parsed_count(self) -> int:
        return len(self.parsed)

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


def request(*sha256s: str, from_experiment: str | None = None, all: bool = False) -> ExperimentRequest:
    return ExperimentRequest("prueba", "", PARAMETERS, list(sha256s), from_experiment, all)


def test_resolve_takes_the_parsed_ones_once_and_sets_aside_the_others() -> None:
    resolution = ExperimentRunner.resolve(Store(A, B), request(B, C, A, B))
    assert (resolution.sha256s, resolution.unparsed) == ([B, A], [C])


def test_resolve_from_another_experiment_takes_its_documents() -> None:
    resolution = ExperimentRunner.resolve(Store(A, used=(A, C)), request(from_experiment="e0"))
    assert (resolution.sha256s, resolution.unparsed) == ([A], [C])


class Unread(Store):
    """Reading a document fails the test: listing the parsed ones must be enough."""

    def document(self, sha256: str) -> ParsedDocument | None:
        raise AssertionError(f"{sha256} was read")


def test_resolve_with_all_takes_every_parsed_document_without_reading_them() -> None:
    assert ExperimentRunner.resolve(Unread(B, A), request(all=True)) == Resolution([A, B], [])


def test_a_resume_of_all_skips_what_it_already_chunked() -> None:
    resolution, kept = ExperimentRunner.pending(Store(A, B, C), request(all=True), [DocumentUse(B, True, 2, [3, 5])])
    assert (resolution.sha256s, [u.sha256 for u in kept]) == ([A, C], [B])


def test_the_experiment_node_says_it_took_every_parsed_document() -> None:
    properties = ExperimentGraph.experiment("e1", request(all=True), 2, "2026").nodes[0].properties
    assert '"all": true' in str(properties["documentos"])


def test_its_start_records_the_total_only_known_then() -> None:
    assert '"files": 7' in str(ExperimentGraph.started("e1", "2026", 7).nodes[0].properties["progreso"])
    assert "progreso" not in ExperimentGraph.started("e1", "2026").nodes[0].properties


def test_a_document_is_recorded_with_its_sections_and_chunks_apart_from_the_official_ones() -> None:
    store = Store(A)
    outcome = ExperimentRunner.run(store, Chunks(), "e1", request(A), ExperimentRunner.resolve(store, request(A)))
    [batch] = store.saved
    document = batch.nodes[0]
    assert (document.key.label, document.key.id) == (GraphLabel.EXP_DOCUMENTO, f"e1:{A}")
    assert (document.properties["sha256"], document.properties["chunks"], document.properties["tokens"]) == (A, 2, 8)
    used = next(link for link in batch.links if link.type is GraphRelation.EXP_DE)
    assert (used.source, used.target.label, used.target.id) == (document.key, GraphLabel.JSON, A)
    owned = {(link.type, link.source.label) for link in batch.links if link.target.label is not GraphLabel.JSON}
    assert owned == {
        (GraphRelation.EXP_TIENE_DOCUMENTO, GraphLabel.EXPERIMENTO),
        (GraphRelation.EXP_TIENE_SECCION, GraphLabel.EXP_DOCUMENTO),
        (GraphRelation.EXP_TIENE_CHUNK, GraphLabel.EXP_SECCION),
    }
    assert {n.key.label for n in batch.nodes[1:]} == {GraphLabel.EXP_SECCION, GraphLabel.EXP_CHUNK}
    assert batch.replace_from == document.key  # only what hung from its document: nothing official is touched
    assert (outcome.results.chunked, outcome.results.chunks, outcome.results.by_document[0].sha256) == (1, 2, A)


def test_a_document_that_fails_is_recorded_and_the_rest_goes_on() -> None:
    store = Store(A, B)
    resolution = ExperimentRunner.resolve(store, request(A, B, C))
    outcome = ExperimentRunner.run(store, Chunks(fail="bad"), "e1", request(A, B, C), resolution)
    assert outcome.error is None and outcome.progress.errors == 2
    assert [f.error for f in outcome.results.failures] == [UNPARSED, "bad", "bad"]
    assert all(b.nodes[0].properties["estado"] == "error" for b in store.saved)
    assert all(len(b.nodes) == 1 for b in store.saved)  # its EXP_DOCUMENTO, without sections


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
    assert properties["documentos"] == f'{{"all": false, "from_experiment": null, "sha256s": ["{A}"]}}'


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
    assert [b.nodes[0].properties["sha256"] for b in store.saved] == [B]  # A isn't chunked again
    assert (outcome.progress.files, outcome.progress.done, outcome.progress.chunks) == (2, 2, 4)
    assert (outcome.results.documents, outcome.results.chunked, outcome.results.chunks) == (3, 2, 4)
    assert outcome.results.tokens is not None and outcome.results.tokens.max == 5
