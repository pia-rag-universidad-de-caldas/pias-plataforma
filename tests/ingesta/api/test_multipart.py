"""The multipart/form-data reader of POST /uploads (feature 049), against bodies encoded by httpx."""

import httpx
import pytest

from ingesta.api.multipart import MultipartError, boundary, parse


def encoded(files: list[tuple[str, tuple[str, bytes]]], data: dict[str, str]) -> tuple[str, bytes]:
    request = httpx.Request("POST", "http://x/uploads", files=files, data=data)
    return request.headers["content-type"], request.read()


def test_binary_content_and_fields_come_back_intact() -> None:
    content = bytes(range(256)) * 10 + b"\r\n--not-a-boundary\r\n"
    kind, body = encoded([("files", ("año.pdf", content))], {"code": "023560"})
    mark = boundary(kind)
    assert mark is not None
    parts = {p.name: p for p in parse(body, mark)}
    assert parts["code"].content == b"023560" and parts["code"].filename is None
    assert parts["files"].content == content and parts["files"].filename == "año.pdf"


def test_an_extended_filename_wins() -> None:
    body = (
        b'--b\r\nContent-Disposition: form-data; name="files"; filename="a.pdf"; filename*=UTF-8\'\'%C3%B1.pdf\r\n'
        b"\r\nx\r\n--b--\r\n"
    )
    assert parse(body, "b")[0].filename == "ñ.pdf"


@pytest.mark.parametrize(
    "kind", ["application/json", "multipart/form-data", "multipart/mixed; boundary=b", "text/plain; boundary=b"]
)
def test_only_multipart_form_data_with_a_boundary_has_one(kind: str) -> None:
    assert boundary(kind) is None


def test_a_body_without_its_closing_boundary_is_malformed() -> None:
    with pytest.raises(MultipartError):
        parse(b'--b\r\nContent-Disposition: form-data; name="code"\r\n\r\n023560', "b")
