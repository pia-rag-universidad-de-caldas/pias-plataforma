"""`prueba-chunking ask "pregunta"` (feature 048): one question to POST /consultas/ask of a server that already runs,
and its answer with its sources, in Spanish. It starts nothing: without a server it says how to start one. With
--attach (repeatable), documents and images go with the question (phase 2): what is similar to them is searched."""

import argparse
import base64
import mimetypes
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, TextIO

import httpx

from common.config import CONSULTAS_PATH

type Json = Any  # the decoded answer of the server (checked where it is read)
type ClientFactory = Callable[[str, float], httpx.Client]

ASK_TIMEOUT = 600.0  # seconds: a local LLM may take minutes on a long context
TEXT_WIDTH = 400  # characters of a source's text shown with --sources

OK, FAILED, NO_SERVER = 0, 1, 2


def _client(url: str, timeout: float) -> httpx.Client:
    return httpx.Client(base_url=url.rstrip("/"), timeout=timeout)


def _detail(response: httpx.Response) -> str:
    try:
        body: Json = response.json()
    except ValueError:
        return response.text[:300] or response.reason_phrase
    if isinstance(body, Mapping):
        found = body.get("detail", body.get("detalle", body))
        return found if isinstance(found, str) else str(found)[:300]
    return str(body)[:300]


class AttachmentError(Exception):
    """A file of --attach can't be read."""


def attachment(path: str) -> dict[str, str]:
    """A file of --attach as POST /consultas/ask receives it: {name, mime, content (base64)}."""
    file = Path(path)
    try:
        content = file.read_bytes()
    except OSError as error:
        raise AttachmentError(f"No se puede leer el adjunto {path}: {error.strerror or error}") from error
    mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    return {"name": file.name, "mime": mime, "content": base64.b64encode(content).decode("ascii")}


def body(args: argparse.Namespace) -> dict[str, object]:
    """What POST /consultas/ask receives from the options; AttachmentError if a file of --attach can't be read."""
    sent: dict[str, object] = {}
    if args.question:
        sent["question"] = args.question
    if args.attach:
        sent["attachments"] = [attachment(path) for path in args.attach]
    if args.k is not None:
        sent["k"] = args.k
    if args.chat:
        sent["chat"] = args.chat
    if args.experiment:
        sent["against"] = {"embeddings_experiment": args.experiment}
    return sent


def _pages(pages: Json) -> str:
    if not isinstance(pages, list) or not pages:
        return ""
    numbers = ", ".join(str(p) for p in pages)
    return f"página {numbers}" if len(pages) == 1 else f"páginas {numbers}"


def source_line(number: int, source: Mapping[str, Json]) -> str:
    """`[1] 2024/03/... · PIAA 020055 · páginas 2, 3 · puntaje 0.71`."""
    score = source.get("score")
    facts = [
        str(source.get("origin") or source.get("sha256") or ""),
        f"PIAA {source['code']}" if source.get("code") else "",
        _pages(source.get("pages")),
        f"puntaje {score:.2f}" if isinstance(score, (int, float)) else "",
    ]
    return f"[{number}] " + " · ".join(f for f in facts if f)


def attachment_line(used: Mapping[str, Json]) -> str:
    """`plan.pdf · documento · 12 trozos (4800 caracteres), leído en parte` or an image's description."""
    pieces = used.get("pieces")
    facts = [str(used.get("name") or ""), str(used.get("kind") or "")]
    if isinstance(pieces, int):
        facts.append(f"{pieces} {'trozo' if pieces == 1 else 'trozos'} ({used.get('characters')} caracteres)")
    if used.get("truncated"):
        facts.append("leído en parte")
    line = " · ".join(f for f in facts if f)
    description = used.get("description")
    return f"{line}\n  {description}" if isinstance(description, str) and description else line


def show(answer: Mapping[str, Json], with_text: bool, out: TextIO) -> None:
    print(str(answer.get("answer") or "").strip(), file=out)
    sources = answer.get("sources")
    sources = [s for s in sources if isinstance(s, Mapping)] if isinstance(sources, list) else []
    print(file=out)
    if not sources:
        print("Sin fuentes: ningún fragmento pasó el puntaje mínimo (no se llamó al LLM).", file=out)
    else:
        print("Fuentes:", file=out)
        for number, source in enumerate(sources, 1):
            print(f"  {source_line(number, source)}", file=out)
            headings = source.get("headings")
            if with_text and isinstance(headings, list) and headings:
                print(f"      {' > '.join(str(h) for h in headings)}", file=out)
            if with_text:
                text = " ".join(str(source.get("text") or "").split())
                print(f"      {text[:TEXT_WIDTH]}{'…' if len(text) > TEXT_WIDTH else ''}", file=out)
    seconds = answer.get("seconds")
    seconds = seconds if isinstance(seconds, Mapping) else {}
    model = answer.get("model") or "sin LLM"
    lab = " · laboratorio" if answer.get("laboratory") else ""
    timing = " · ".join(
        f"{name} {value:.1f} s"
        for name, value in (("búsqueda", seconds.get("search")), ("respuesta", seconds.get("answer")))
        if isinstance(value, (int, float))
    )
    attachments = answer.get("attachments")
    for used in attachments if isinstance(attachments, list) else []:
        if isinstance(used, Mapping):
            print(file=out)
            print(f"Adjunto: {attachment_line(used)}", file=out)
    print(file=out)
    print(f"Modelo: {model}{lab}" + (f" · {timing}" if timing else ""), file=out)
    print(f"Chat: {answer.get('chat')} (para seguir la conversación: --chat {answer.get('chat')})", file=out)


def _failure(response: httpx.Response, url: str) -> str:
    detail = _detail(response)
    if response.status_code == 503:
        return f"Un módulo no responde: {detail}"
    if response.status_code == 404 and detail == "Not Found":
        return f"El servidor de {url} no tiene {CONSULTAS_PATH}: ¿es una versión anterior a la 048?"
    if response.status_code == 404:
        return f"No se encontró: {detail}"
    if response.status_code == 413:
        return f"Los adjuntos pesan demasiado para el servidor: {detail}"
    if response.status_code == 422:
        return f"La pregunta no es válida: {detail}"
    return f"El servidor respondió {response.status_code}: {detail}"


def ask(
    args: argparse.Namespace,
    client: ClientFactory = _client,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """0 with the answer; 1 if the server answered an error; 2 if there is no server at --url. Without out and err,
    the standard ones when this runs."""
    out, err = out or sys.stdout, err or sys.stderr
    if not args.question and not args.attach:
        print("Falta la pregunta (o algún --attach).", file=err)
        return FAILED
    try:
        sent = body(args)
    except AttachmentError as error:
        print(error, file=err)
        return FAILED
    try:
        with client(args.url, args.timeout) as http:
            response = http.post(f"{CONSULTAS_PATH}/ask", json=sent)
    except httpx.TimeoutException:
        print(f"El servidor de {args.url} no respondió en {args.timeout:.0f} s (prueba con --timeout).", file=err)
        return FAILED
    except httpx.HTTPError as error:
        print(
            f"No hay un servidor en {args.url} ({error}). Levántalo con `prueba-chunking serve` (o la consola) "
            "o di dónde está con --url.",
            file=err,
        )
        return NO_SERVER
    if not response.is_success:
        print(_failure(response, args.url), file=err)
        return FAILED
    try:
        answer: Json = response.json()
    except ValueError:
        answer = None
    if not isinstance(answer, Mapping):
        print(f"El servidor respondió algo que no es una respuesta: {response.text[:300]}", file=err)
        return FAILED
    show(answer, args.sources, out)
    return OK


def add_parser(sub: "argparse._SubParsersAction[argparse.ArgumentParser]", default_url: str) -> None:
    parser = sub.add_parser(
        "ask", help="asks a question to a running server (POST /consultas/ask) and shows the answer"
    )
    parser.add_argument("question", nargs="?", default="", help="the question, in quotes (optional with --attach)")
    parser.add_argument("--k", type=int, help="how many chunks to search (default: the configuration's)")
    parser.add_argument("--chat", help="the id of a chat to go on with (its last turns go to the LLM)")
    parser.add_argument("--experiment", help="ask the chunks of a finished embeddings experiment (laboratory)")
    parser.add_argument(
        "--attach",
        action="append",
        metavar="FILE",
        help="a document (pdf, docx, doc) or image (png, jpg, webp) to search what is similar to it; repeatable",
    )
    parser.add_argument("--url", default=default_url, help=f"where the server is (default {default_url})")
    parser.add_argument("--sources", action="store_true", help="also show the text of each source")
    parser.add_argument(
        "--timeout", type=float, default=ASK_TIMEOUT, help=f"seconds to wait (default {ASK_TIMEOUT:.0f})"
    )
    parser.set_defaults(function=ask)
