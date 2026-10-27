"""ExperimentRunner (feature 025) over fake ports: which files enter an experiment (resolve) and what running it
records (run). The fakes implement only the role each step asks for (SelectionStore, RecordingStore)."""

from collections.abc import Iterator

from chunking.domain import ExperimentGraph, ExperimentRunner, Parameters, Planner
from chunking.models import (
    ChunkedDocument,
    ChunkingParameters,
    ChunkingStrategy,
    ChunkPiece,
    ConversionError,
    ConversionParameters,
    ConvertedDocument,
    Converter,
    DocumentError,
    DocumentFilter,
    DocumentSection,
    DocumentStatus,
    Element,
    ElementKind,
    ExperimentDocument,
    ExperimentFile,
    ExperimentOutcome,
    ExperimentRequest,
    FileResolution,
    FileSelection,
    GraphBatch,
    GraphLabel,
    Inclusion,
    Match,
    OfficialDocument,
    Plan,
    RequestedStrategy,
    Rule,
    SourceDocument,
    StrategyParameters,
    TableMode,
)

CONVERSION = ConversionParameters(1, False, True, TableMode.ACCURATE, Inclusion(), "2")


def doc(n: int, sha: str | None = "") -> SourceDocument:
    return SourceDocument(f"2024/{n}.pdf", f"v/{n}.pdf", f"{n}.pdf", f"h{n}" if sha == "" else sha, "pdf", 2024, None)


class Source:
    def __init__(self, *pages: list[SourceDocument]) -> None:
        self._pages = pages

    def pages(
        self, filter: DocumentFilter, per_page: int, first: int = 1, last: int | None = None
    ) -> Iterator[list[SourceDocument]]:
        yield from self._pages[first - 1 : last]

    def find(self, sha256: str) -> SourceDocument:
        found = [d for p in self._pages for d in p if d.sha256 == sha256]
        if not found:
            raise DocumentError(f"no file with {sha256}")
        return found[0]

    def content(self, document: SourceDocument) -> bytes:
        return document.name.encode()


class Selection:
    """SelectionStore: one earlier experiment, and the conversions already stored."""

    def __init__(self, stored: set[str], earlier: dict[str, SourceDocument | None]) -> None:
        self._stored, self._earlier = stored, earlier

    def documents(self, experiment_id: str) -> list[ExperimentDocument]:
        return [
            ExperimentDocument(sha, f"{sha}:f", None, None, None, True, DocumentStatus.CHUNKED, None, 1, 1)
            for sha in self._earlier
        ]

    def source(self, conversion_id: str) -> SourceDocument | None:
        return self._earlier[conversion_id.split(":")[0]]

    def has_conversion(self, conversion_id: str) -> bool:
        return conversion_id in self._stored

    def official(self, sha256: str) -> OfficialDocument | None:
        return None

    def official_pages(
        self, per_page: int, first: int = 1, last: int | None = None
    ) -> Iterator[list[OfficialDocument]]:
        yield from ()


def resolve(files: FileSelection, store: Selection | None = None) -> FileResolution:
    request = ExperimentRequest("e", "", files, CONVERSION, None)
    source = Source([doc(1), doc(2)], [doc(2), doc(3, sha=None)], [doc(4)])
    return ExperimentRunner.resolve(source, store or Selection(set(), {}), request, 2)


def test_sha256s_once_each_and_an_unknown_one_fails_alone() -> None:
    resolution = resolve(FileSelection(sha256s=["h2", "h1", "h2", "nope"]))
    assert [f.document.origin for f in resolution.files] == ["2024/2.pdf", "2024/1.pdf"]
    assert [(f.sha256, f.origin) for f in resolution.failures] == [("nope", None)]


def test_a_limit_across_pages_without_repeating_a_content_nor_taking_one_without_sha256() -> None:
    resolution = resolve(FileSelection(filter=DocumentFilter(), limit=4))
    assert [f.document.origin for f in resolution.files] == ["2024/1.pdf", "2024/2.pdf"]  # 2 twice: once
    assert [f.origin for f in resolution.failures] == ["2024/3.pdf"]


def test_the_conversion_is_reused_when_its_fingerprint_is_stored() -> None:
    stored = {ExperimentGraph.conversion_id("h1", CONVERSION)}
    resolution = resolve(FileSelection(sha256s=["h1", "h2"]), Selection(stored, {}))
    assert [f.reused for f in resolution.files] == [True, False]


def test_from_an_earlier_experiment_its_documents_and_the_lost_ones_fail() -> None:
    resolution = resolve(FileSelection(from_experiment="old"), Selection(set(), {"h4": doc(4), "h9": None}))
    assert [f.document.origin for f in resolution.files] == ["2024/4.pdf"]
    assert [f.error for f in resolution.failures] == ["its conversion is no longer in the graph"]


# --- run ---

CONTENT = ConvertedDocument(
    "t",
    [
        DocumentSection("Objetivos", 1, [1], [Element(ElementKind.PARAGRAPH, "uno dos", [1])]),
        DocumentSection("Bibliografía", 1, [2], [Element(ElementKind.PARAGRAPH, "tres", [2])]),
    ],
)


class Recording:
    """RecordingStore: what was saved, and the conversions already there."""

    def __init__(self, stored: dict[str, ConvertedDocument]) -> None:
        self._stored = stored
        self.saved: list[GraphBatch] = []

    def save(self, batch: GraphBatch) -> None:
        self.saved.append(batch)

    def conversion(self, conversion_id: str) -> ConvertedDocument | None:
        return self._stored.get(conversion_id)

    def labels(self) -> list[str]:
        return [n.key.label.value for b in self.saved for n in b.nodes if n.key.label != GraphLabel.EXPERIMENTO]


class Docling(Converter):
    def available(self) -> bool:
        return True

    def version(self) -> str | None:
        return "2"

    def chunk(self, name: str, content: bytes, parameters: ChunkingParameters) -> ChunkedDocument:
        raise AssertionError("experiments only convert")

    def convert(self, name: str, content: bytes, parameters: ConversionParameters) -> ConvertedDocument:
        if name == "bad.pdf":
            raise ConversionError("broken PDF")
        return CONTENT


class Words:
    """SectionChunker: one piece per word, as many tokens as letters."""

    def available(self) -> bool:
        return True

    def chunk(self, section: DocumentSection, parameters: StrategyParameters) -> list[ChunkPiece]:
        words = [w for e in section.elements for w in e.text.split()]
        return [ChunkPiece(w, [section.title], section.pages, len(w)) for w in words]


def experiment(
    files: list[ExperimentFile], plan: Plan | None, stored: dict[str, ConvertedDocument] | None = None
) -> tuple[ExperimentOutcome, Recording]:
    store = Recording(stored or {})
    request = ExperimentRequest("e", "", FileSelection(sha256s=["x"]), CONVERSION, plan)
    resolution = FileResolution(files, [])
    outcome = ExperimentRunner.run(Source(), store, Docling(), Words(), "exp1", request, resolution, lambda _: None)
    return outcome, store


def file(n: int, reused: bool = False, name: str | None = None) -> ExperimentFile:
    document = doc(n) if name is None else SourceDocument(f"2024/{name}", "v", name, f"h{n}", "pdf", 2024, None)
    return ExperimentFile(document, reused, f"h{n}:f")


def plan(max_tokens: int = 512) -> Plan:
    points = Parameters.resolve(RequestedStrategy(strategy=ChunkingStrategy.POINTS, max_tokens=max_tokens))
    return Plan([Rule(Match(titles=["objetivos"]), points)], Parameters.resolve(RequestedStrategy()))


def test_converts_or_reuses_then_cuts_each_section_by_its_rule() -> None:
    outcome, store = experiment([file(1), file(2, reused=True)], plan(), {"h2:f": CONTENT})
    progress = outcome.progress
    assert (progress.done, progress.converted, progress.reused, progress.sections, progress.chunks) == (2, 1, 1, 4, 6)
    results = outcome.results
    assert set(results.by_strategy) == {"points", "hybrid"} and set(results.by_rule) == {"0", "default"}
    assert results.by_rule["0"].chunks == 4 and results.by_rule["default"].chunks == 2
    # Only the new conversion is written; the reused one is only linked (EXP_USA).
    assert store.labels().count("EXP_DOCUMENTO") == 1 and store.labels().count("EXP_CHUNK") == 6


def test_a_failed_conversion_records_it_and_the_experiment_goes_on() -> None:
    outcome, store = experiment([file(1, name="bad.pdf"), file(2)], plan())
    assert [f.error for f in outcome.results.failures] == ["broken PDF"]
    assert (outcome.progress.errors, outcome.progress.done, outcome.progress.converted) == (1, 2, 1)
    failed = next(n for b in store.saved for n in b.nodes if n.key.label == GraphLabel.EXP_DOCUMENTO)
    assert failed.properties["estado"] == "error"


def test_a_chunk_over_max_tokens_fails_the_document_without_counting_its_sections() -> None:
    long = ConvertedDocument("t", [DocumentSection("Objetivos", 1, [1], [Element(ElementKind.PARAGRAPH, "x" * 20)])])
    outcome, _ = experiment([file(1, reused=True)], plan(max_tokens=16), {"h1:f": long})
    assert outcome.results.failures[0].error == "section 0: a chunk has more than 16 tokens"
    assert outcome.progress.sections == 0 and outcome.results.by_strategy == {}


def test_without_a_plan_it_only_converts() -> None:
    outcome, store = experiment([file(1)], None)
    assert (outcome.progress.converted, outcome.progress.sections) == (1, 0)
    assert "EXP_SECCION" not in store.labels()


def test_the_document_batch_has_deterministic_ids_in_order() -> None:
    [assignment] = Planner.assign(ConvertedDocument("t", CONTENT.sections[:1]), plan())
    pieces = [ChunkPiece("uno", ["Objetivos"], [1], 3), ChunkPiece("dos", ["Objetivos"], [1], 3)]
    batch = ExperimentGraph.document("exp1", doc(1), "h1", "h1:f", False, [(assignment, pieces)], None, 0.5)
    assert [n.key.id for n in batch.nodes] == ["exp1:h1:0", "exp1:h1:0:0", "exp1:h1:0:1"]
    assert [link.type.value for link in batch.links] == [
        "EXP_USA",
        "EXP_GENERA",
        "EXP_TIENE_SECCION",
        "EXP_TIENE_CHUNK",
        "EXP_TIENE_CHUNK",
    ]
    assert batch.links[0].properties["chunks"] == 2 and batch.nodes[0].properties["regla"] == "0"
