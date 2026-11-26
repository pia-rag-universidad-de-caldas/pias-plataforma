"""HttpRawStore (feature 042): the RAW nodes of data over HTTP, on a data that keeps them in a dict."""

import base64
from dataclasses import replace

import pytest
from fakes import FakeData

from ingesta.adapters import HttpRawStore
from ingesta.models import FileRecord, RawFileRejected, RawStoreError

RECORD = FileRecord(
    "2024/01/S/020055/a.pdf",
    "vigentes/pdf/a.pdf",
    2024,
    "01",
    1,
    "S",
    "020055",
    "a.pdf",
    "pdf",
    3,
    "2024-01-01",
    "2024-01-02",
    "copiado",
    "h1",
    True,
    mime="application/pdf",
)


def test_a_file_is_published_with_its_content_and_where_it_comes_from(fake_data: FakeData) -> None:
    HttpRawStore(fake_data.client(), "/data").publish(RECORD, b"pdf", "2026-11-09")
    stored = fake_data.nodes[("RAW", "h1")]
    assert base64.b64decode(str(stored["contenido"])) == b"pdf"
    assert (stored["codigo"], stored["vigente"], stored["subido_en"]) == ("020055", True, "2026-11-09")
    nodes = fake_data.batches[0]["nodes"]
    assert isinstance(nodes, list) and nodes[0]["mode"] == "merge"


def test_publishing_again_keeps_what_parsing_wrote(fake_data: FakeData) -> None:
    fake_data.nodes[("RAW", "h1")] = {"estado_parseo": "parseado"}
    HttpRawStore(fake_data.client(), "/data").publish(RECORD, b"pdf", "at")
    assert fake_data.nodes[("RAW", "h1")]["estado_parseo"] == "parseado"


def test_which_ones_data_has_is_read_without_their_content(fake_data: FakeData) -> None:
    store = HttpRawStore(fake_data.client(), "/data")
    store.publish(RECORD, b"pdf", "at")
    store.publish(replace(RECORD, sha256="h2"), b"pdf", "at")
    store.retire(["h2"])
    assert store.published() == {"h1": True, "h2": False}


def test_a_file_data_refuses_is_only_that_file(fake_data: FakeData) -> None:
    fake_data.refuse.add("h1")
    with pytest.raises(RawFileRejected):
        HttpRawStore(fake_data.client(), "/data").publish(RECORD, b"pdf", "at")


def test_data_down_stops_the_publication(fake_data: FakeData) -> None:
    fake_data.down = True
    with pytest.raises(RawStoreError):
        HttpRawStore(fake_data.client(), "/data").published()
