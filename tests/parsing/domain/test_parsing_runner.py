"""ParsingRunner (feature 042): a run over the sha256 it is given, with fake ports: what it skips, what it parses,
what it resumes and what stops it."""

from collections.abc import Iterator, Mapping, Sequence

import pytest

from parsing.domain import ParsingRunner
from parsing.models import (
    DocumentError,
    DocumentState,
    GraphBatch,
    GraphLabel,
    PageCoverage,
    ParsedOutput,
    ParseError,
    Parser,
    ParserUnavailable,
    ParseStatus,
    ParsingRequest,
    RawFile,
    RawState,
    SinkError,
    StoredParse,
)

DOCUMENT = {"schema_name": "DoclingDocument"}


class Raws:
    def __init__(self, states: Mapping[str, RawState]) -> None:
        self._states = states

    def states(self, sha256s: Sequence[str]) -> Mapping[str, RawState]:
        return {s: self._states[s] for s in sha256s if s in self._states}

    def all_states(self) -> Iterator[RawState]:
        yield from self._states.values()

    def get(self, sha256: str) -> RawFile | None:
        return RawFile(sha256, f"{sha256}.pdf", "pdf", "020055", b"%PDF") if sha256 in self._states else None


class Sink:
    def __init__(self, previous: StoredParse | None = None, refuse: bool = False) -> None:
        self.saved: list[GraphBatch] = []
        self._previous, self._refuse = previous, refuse

    def previous(self, sha256: str) -> StoredParse | None:
        return self._previous

    def save(self, batch: GraphBatch) -> None:
        if self._refuse and any(n.key.label is GraphLabel.JSON for n in batch.nodes):
            raise DocumentError("too big")
        self.saved.append(batch)


class FakeParser(Parser):
    def __init__(self, fails: Exception | None = None, coverage: PageCoverage | None = None) -> None:
        self.parsed: list[tuple[str, StoredParse | None]] = []
        self._fails, self._coverage = fails, coverage or PageCoverage(1, 1)

    def available(self) -> bool:
        return True

    def ocr_available(self) -> bool:
        return True

    def version(self) -> str | None:
        return "2.148.0"

    def parse(self, name: str, content: bytes, previous: StoredParse | None = None) -> ParsedOutput:
        if self._fails:
            raise self._fails
        self.parsed.append((name, previous))
        return ParsedOutput(DOCUMENT, self._coverage)


def run(
    request: ParsingRequest, states: Mapping[str, RawState], parser: Parser, sink: Sink | None = None
) -> tuple[list[DocumentState], Sink]:
    sink = sink or Sink()
    found: list[DocumentState] = []
    outcome = ParsingRunner.run(
        request, Raws(states), sink, parser, "f1", lambda: "at", lambda: 0.0, lambda r, _: found.append(r.state)
    )
    assert outcome.progress.done == len(found)
    return found, sink


def test_each_sha256_once_skipping_what_is_done_and_what_data_doesnt_have() -> None:
    states = {"a": RawState("a", True, ParseStatus.PARSED, "f1"), "b": RawState("b")}
    found, sink = run(ParsingRequest(["a", "b", "c", "b"]), states, FakeParser())
    assert found == [DocumentState.SKIPPED, DocumentState.PARSED, DocumentState.MISSING]
    assert len(sink.saved) == 1


def test_redo_parses_again_what_was_done() -> None:
    found, _ = run(ParsingRequest(["a"], redo=True), {"a": RawState("a", True, ParseStatus.PARSED, "f1")}, FakeParser())
    assert found == [DocumentState.PARSED]


def test_simulate_parses_nothing() -> None:
    parser = FakeParser()
    found, sink = run(ParsingRequest(["a"], simulate=True), {"a": RawState("a")}, parser)
    assert (found, sink.saved, parser.parsed) == ([DocumentState.SIMULATED], [], [])


def test_a_partial_one_of_this_fingerprint_resumes() -> None:
    previous = StoredParse(DOCUMENT, PageCoverage(3, 2, [3]), ParseStatus.PARTIAL, "f1")
    parser = FakeParser()
    found, _ = run(ParsingRequest(["a"]), {"a": RawState("a", True, ParseStatus.PARTIAL, "f1")}, parser, Sink(previous))
    assert found == [DocumentState.PARSED] and parser.parsed[0][1] == previous


@pytest.mark.parametrize("fingerprint", ["other", "f1"])
def test_a_partial_one_starts_over_with_another_fingerprint_or_with_redo(fingerprint: str) -> None:
    previous = StoredParse(DOCUMENT, PageCoverage(3, 2, [3]), ParseStatus.PARTIAL, fingerprint)
    parser = FakeParser()
    run(ParsingRequest(["a"], redo=fingerprint == "f1"), {"a": RawState("a")}, parser, Sink(previous))
    assert parser.parsed[0][1] is None


def test_a_document_that_stops_early_is_partial() -> None:
    found, _ = run(ParsingRequest(["a"]), {"a": RawState("a")}, FakeParser(coverage=PageCoverage(2, 1, [2], [], "t")))
    assert found == [DocumentState.PARTIAL]


@pytest.mark.parametrize(("parser", "refuse"), [(FakeParser(ParseError("corrupt")), False), (FakeParser(), True)])
def test_a_documents_failure_is_noted_on_its_raw_and_the_run_goes_on(parser: FakeParser, refuse: bool) -> None:
    states = {"a": RawState("a"), "b": RawState("b")}
    found, sink = run(ParsingRequest(["a", "b"]), states, parser, Sink(refuse=refuse))
    assert found == [DocumentState.ERROR, DocumentState.ERROR]
    assert all(n.key.label is GraphLabel.RAW for batch in sink.saved for n in batch.nodes)


@pytest.mark.parametrize("error", [ParserUnavailable("no models"), SinkError("data down")])
def test_the_machine_or_data_down_stops_the_run(error: Exception) -> None:
    parser = FakeParser(error) if isinstance(error, ParserUnavailable) else FakeParser()

    class Down(Sink):
        def save(self, batch: GraphBatch) -> None:
            raise error

    outcome = ParsingRunner.run(
        ParsingRequest(["a", "b"]), Raws({"a": RawState("a"), "b": RawState("b")}), Down(), parser, "f1",
        lambda: "at", lambda: 0.0,
    )  # fmt: skip
    assert outcome.error and outcome.progress.done == 0
