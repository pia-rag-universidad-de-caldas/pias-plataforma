"""POST /parsing/preview (feature 048) with a fake parser: JSON and multipart bodies, the limits, the errors, and
that nothing reaches data."""

import base64
import threading
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest
from fakes import FakeData
from fastapi.testclient import TestClient

from parsing.adapters import HttpSession
from parsing.api import ApiSettings, create_app
from parsing.config import PREVIEW_MAX_BYTES, PREVIEW_MAX_PAGES
from parsing.models import PageCoverage, ParsedOutput, ParseError, Parser, ParserUnavailable, StoredParse

DOCUMENT = {
    "body": {"children": [{"$ref": "#/texts/0"}, {"$ref": "#/texts/1"}]},
    "texts": [
        {"label": "section_header", "level": 1, "text": "Evaluación", "children": []},
        {"label": "text", "text": "Dos parciales.", "prov": [{"page_no": 1}], "children": []},
    ],
}


@dataclass(frozen=True)
class FakeSettings(ApiSettings):
    data: FakeData | None = None

    def session(self) -> HttpSession:
        assert self.data is not None
        return HttpSession(self.self_url, self.data_path, transport=httpx.MockTransport(self.data.handle))


class PreviewParser(Parser):
    def __init__(self, error: Exception | None = None, total: int = 1, installed: bool = True) -> None:
        self.error, self.total, self.installed = error, total, installed
        self.asked: list[tuple[str, int]] = []
        self.release: threading.Event | None = None

    def available(self) -> bool:
        return self.installed

    def ocr_available(self) -> bool:
        return self.installed

    def version(self) -> str | None:
        return "2.149.0" if self.installed else None

    def parse(self, name: str, content: bytes, previous: StoredParse | None = None) -> ParsedOutput:
        raise AssertionError("a preview never runs a parse")

    def preview(self, name: str, content: bytes, max_pages: int) -> ParsedOutput:
        self.asked.append((name, max_pages))
        if self.release is not None:
            self.release.wait(5)
        if self.error is not None:
            raise self.error
        return ParsedOutput(DOCUMENT, PageCoverage(self.total, min(self.total, max_pages)))


@pytest.fixture
def parser() -> PreviewParser:
    return PreviewParser()


@pytest.fixture
def client(fake_data: FakeData, parser: PreviewParser) -> Iterator[TestClient]:
    with TestClient(create_app(FakeSettings("http://server", data=fake_data), parser)) as test_client:
        yield test_client


def body(name: str = "plan.pdf", content: bytes = b"%PDF-1.4", mime: str | None = None) -> dict[str, object]:
    sent: dict[str, object] = {"name": name, "content": base64.b64encode(content).decode()}
    if mime is not None:
        sent["mime"] = mime
    return sent


def test_a_preview_answers_the_text_by_sections_and_stores_nothing(
    client: TestClient, parser: PreviewParser, fake_data: FakeData
) -> None:
    answer = client.post("/preview", json=body())
    assert answer.status_code == 200
    found = answer.json()
    assert (found["name"], found["pages"], found["truncated"]) == ("plan.pdf", 1, False)
    assert found["sections"] == [{"headings": ["Evaluación"], "text": "Dos parciales.", "pages": [1]}]
    assert found["text"] == "Evaluación\nDos parciales."
    assert parser.asked == [("plan.pdf", PREVIEW_MAX_PAGES)] and fake_data.nodes == {}


def test_a_multipart_file_is_previewed_too(client: TestClient, parser: PreviewParser) -> None:
    files = {"file": ("plan.docx", b"PK\x03\x04", "application/octet-stream")}
    assert client.post("/preview", files=files).status_code == 200
    assert parser.asked[-1][0] == "plan.docx"


def test_the_mime_gives_the_extension_of_a_name_without_one(client: TestClient, parser: PreviewParser) -> None:
    assert client.post("/preview", json=body("plan", mime="application/pdf")).status_code == 200
    assert parser.asked[-1][0] == "plan.pdf"


def test_a_long_pdf_is_truncated(fake_data: FakeData) -> None:
    app = create_app(FakeSettings("http://server", data=fake_data), PreviewParser(total=PREVIEW_MAX_PAGES + 5))
    with TestClient(app) as client:
        assert client.post("/preview", json=body()).json()["truncated"] is True


@pytest.mark.parametrize(
    ("sent", "code"),
    [
        (body("foto.png", mime="image/png"), 415),
        (body(content=b""), 422),
        ({**body(), "content": "no es base64!"}, 422),
        ({**body(), "other": 1}, 422),
    ],
    ids=["not a document", "empty", "not base64", "unknown key"],
)
def test_a_wrong_body_is_refused(client: TestClient, sent: dict[str, object], code: int) -> None:
    assert client.post("/preview", json=sent).status_code == code


def test_a_file_over_the_limit_is_413(client: TestClient, parser: PreviewParser) -> None:
    assert client.post("/preview", json=body(content=b"x" * (PREVIEW_MAX_BYTES + 1))).status_code == 413
    assert parser.asked == []


def test_another_content_type_is_415(client: TestClient) -> None:
    assert client.post("/preview", content=b"%PDF", headers={"content-type": "application/pdf"}).status_code == 415


@pytest.mark.parametrize(
    ("error", "code"),
    [(ParseError("corrupt"), 422), (ParserUnavailable("no memory"), 503)],
    ids=["the document's fault", "the machine's"],
)
def test_a_parser_error_has_its_code(fake_data: FakeData, error: Exception, code: int) -> None:
    with TestClient(create_app(FakeSettings("http://server", data=fake_data), PreviewParser(error))) as client:
        assert client.post("/preview", json=body()).status_code == code


def test_without_docling_it_is_503(fake_data: FakeData) -> None:
    with TestClient(
        create_app(FakeSettings("http://server", data=fake_data), PreviewParser(installed=False))
    ) as client:
        assert client.post("/preview", json=body()).status_code == 503


def test_one_preview_at_a_time(client: TestClient, parser: PreviewParser) -> None:
    parser.release = threading.Event()
    first = threading.Thread(target=lambda: client.post("/preview", json=body()))
    first.start()
    try:
        for _ in range(200):
            if parser.asked:
                break
            threading.Event().wait(0.01)
        assert client.post("/preview", json=body()).status_code == 409
    finally:
        parser.release.set()
        first.join(5)
