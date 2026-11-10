"""`prueba-chunking ask`: what it sends to POST /consultas/ask and what it prints, with a fake transport."""

import base64
import io
import json
from pathlib import Path

import httpx
import pytest

from server.ask import FAILED, NO_SERVER, OK, ask
from server.cli import create_parser, main

ANSWER = {
    "answer": "Con dos parciales y un proyecto [1].",
    "sources": [
        {
            "id": "f1",
            "score": 0.81,
            "text": "Dos parciales (60 %) y un proyecto (40 %).",
            "headings": ["Evaluación"],
            "pages": [3],
            "sha256": "a" * 64,
            "origin": "2024/03/s1/020055/piaa.pdf",
            "code": "020055",
        }
    ],
    "chat": "c1",
    "consulta": "q1",
    "model": "qwen2.5:7b",
    "found": True,
    "seconds": {"search": 0.2, "answer": 3.4},
}


def run(arguments: list[str], handler: httpx.MockTransport) -> tuple[int, str, str]:
    args = create_parser().parse_args(["ask", *arguments])
    out, err = io.StringIO(), io.StringIO()

    def client(url: str, timeout: float) -> httpx.Client:
        return httpx.Client(base_url=url, timeout=timeout, transport=handler)

    return ask(args, client, out, err), out.getvalue(), err.getvalue()


def answering(status: int, body: object, sent: list[object] | None = None) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/consultas/ask"
        if sent is not None:
            sent.append(json.loads(request.content))
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handle)


def test_ask_prints_the_answer_and_its_sources() -> None:
    sent: list[object] = []
    code, out, _ = run(["¿Cómo se evalúa?", "--k", "3", "--chat", "c0"], answering(200, ANSWER, sent))
    assert code == OK and sent == [{"question": "¿Cómo se evalúa?", "k": 3, "chat": "c0"}]
    assert (
        "Con dos parciales" in out and "[1] 2024/03/s1/020055/piaa.pdf · PIAA 020055 · página 3 · puntaje 0.81" in out
    )
    assert "--chat c1" in out and "Dos parciales (60 %)" not in out


def test_sources_shows_their_text() -> None:
    _, out, _ = run(["a", "--sources"], answering(200, ANSWER))
    assert "Evaluación" in out and "Dos parciales (60 %)" in out


def test_an_answer_without_sources_says_so() -> None:
    _, out, _ = run(["a"], answering(200, {**ANSWER, "sources": [], "found": False, "model": None}))
    assert "Sin fuentes" in out and "sin LLM" in out


def test_a_module_down_says_which() -> None:
    code, _, err = run(["a"], answering(503, {"detail": "llm is not answering: Ollama"}))
    assert code == FAILED and "Un módulo no responde: llm is not answering" in err


def test_without_a_server_it_says_how_to_start_one() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    code, _, err = run(["a", "--url", "http://127.0.0.1:1"], httpx.MockTransport(refuse))
    assert code == NO_SERVER and "prueba-chunking serve" in err


def test_ask_is_a_command_of_the_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.argv", ["prueba-chunking", "ask", "hola", "--url", "http://127.0.0.1:1", "--timeout", "2"])
    assert main() == NO_SERVER and "No hay un servidor" in capsys.readouterr().err


def test_attach_sends_each_file_in_base64_with_its_type(tmp_path: Path) -> None:
    (tmp_path / "plan.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "foto.png").write_bytes(b"\x89PNG")
    sent: list[object] = []
    used = {"name": "plan.pdf", "kind": "documento", "pieces": 3, "characters": 900, "truncated": True}
    arguments = ["--attach", str(tmp_path / "plan.pdf"), "--attach", str(tmp_path / "foto.png")]
    code, out, _ = run(arguments, answering(200, {**ANSWER, "attachments": [used]}, sent))
    assert code == OK and sent == [
        {
            "attachments": [
                {"name": "plan.pdf", "mime": "application/pdf", "content": base64.b64encode(b"%PDF-1.4").decode()},
                {"name": "foto.png", "mime": "image/png", "content": base64.b64encode(b"\x89PNG").decode()},
            ]
        }
    ]
    assert "Adjunto: plan.pdf · documento · 3 trozos (900 caracteres) · leído en parte" in out


def test_an_attachment_that_cant_be_read_sends_nothing(tmp_path: Path) -> None:
    sent: list[object] = []
    code, _, err = run(["a", "--attach", str(tmp_path / "no.pdf")], answering(200, ANSWER, sent))
    assert code == FAILED and sent == [] and "No se puede leer el adjunto" in err


def test_without_question_nor_attachment_it_asks_for_one() -> None:
    sent: list[object] = []
    code, _, err = run([], answering(200, ANSWER, sent))
    assert code == FAILED and sent == [] and "Falta la pregunta" in err
