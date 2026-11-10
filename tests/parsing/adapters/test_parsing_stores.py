"""The ports of parsing over data (feature 042), on a data that keeps its nodes in a dict."""

import base64

import pytest
from fakes import FakeData

from parsing.adapters import DataClient, GraphRunStore, HttpParsedSink, HttpRawSource
from parsing.domain import ParsedGraph
from parsing.models import PageCoverage, ParsedOutput, ParseStatus, RawFile, RawState, SinkError, StoredParse

SHA = "a" * 64
DOCUMENT = {"schema_name": "DoclingDocument", "texts": []}


@pytest.fixture
def data(fake_data: FakeData) -> DataClient:
    content = base64.b64encode(b"%PDF").decode()
    fake_data.nodes[("RAW", SHA)] = {"nombre": "plan.pdf", "tipo": "pdf", "codigo": "020055", "contenido": content}
    fake_data.nodes[("RAW", "b" * 64)] = {"vigente": False, "estado_parseo": "parseado", "fingerprint_parseo": "f1"}
    return DataClient(fake_data.client(), "/data")


def test_the_states_are_read_without_the_content(data: DataClient) -> None:
    source = HttpRawSource(data)
    assert source.states([SHA, "c" * 64]) == {SHA: RawState(SHA)}
    assert sorted(source.all_states(), key=lambda s: s.sha256)[1] == RawState("b" * 64, False, ParseStatus.PARSED, "f1")


def test_a_raw_is_read_with_its_file(data: DataClient) -> None:
    assert HttpRawSource(data).get(SHA) == RawFile(SHA, "plan.pdf", "pdf", "020055", b"%PDF")
    assert HttpRawSource(data).get("c" * 64) is None


def test_what_is_written_is_read_back_to_resume(data: DataClient, fake_data: FakeData) -> None:
    sink = HttpParsedSink(data)
    raw = RawFile(SHA, "plan.pdf", "pdf", "020055", b"%PDF")
    output = ParsedOutput(DOCUMENT, PageCoverage(3, 2, [3], reason="timeout"))
    sink.save(ParsedGraph.parsed(raw, output, "f1", "2", "at", 1.0))
    previous = sink.previous(SHA)
    assert previous == StoredParse(DOCUMENT, PageCoverage(3, 2, [3], reason="timeout"), ParseStatus.PARTIAL, "f1")
    assert fake_data.nodes[("RAW", SHA)]["contenido"]  # the file stays: the RAW is merged
    assert ("VIENE_DE", "JSON", SHA, "RAW", SHA) in fake_data.links


def test_a_json_of_before_this_module_isnt_resumed(data: DataClient, fake_data: FakeData) -> None:
    fake_data.nodes[("JSON", SHA)] = {"estado": "convertido", "contenido": "{}"}
    assert HttpParsedSink(data).previous(SHA) is None


def test_the_runs_are_kept_as_their_json(data: DataClient) -> None:
    store = GraphRunStore(data)
    store.save("r1", "finished", "2026-11-09", '{"id": "r1"}')
    assert (store.details(), store.detail("r1"), store.detail("r2")) == (['{"id": "r1"}'], '{"id": "r1"}', None)


def test_data_down_is_a_sink_error(fake_data: FakeData) -> None:
    fake_data.down = True
    with pytest.raises(SinkError):
        HttpRawSource(DataClient(fake_data.client(), "/data")).states([SHA])
