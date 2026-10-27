"""Project entry point (`prueba-chunking` command, feature 020).

    uv run prueba-chunking organize             # copies what is new in data/base/ and classifies data/ingesta/
    uv run prueba-chunking organize --simulate  # shows what it would do, without touching anything
    NEO4J_PASSWORD=... uv run prueba-chunking serve   # every module at http://127.0.0.1:8000:
                                                      # /ingesta, /data, /chunking, /pipeline (docs at <prefix>/docs)

organize is the one of ingesta (see `python -m ingesta --help`). The Neo4j password is read from the
NEO4J_PASSWORD environment variable; if missing and there is a console, it is prompted for without echo. Without a
password (or without the `data` extra, or with Neo4j down) the server starts anyway and /data answers 503.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Callable

from data.api import ApiSettings as DataSettings
from data.config import NEO4J_DATABASE, NEO4J_URL, NEO4J_USER, PASSWORD_VARIABLE
from ingesta.adapters import visible_url
from ingesta.cli import add_organize_command, add_serve_command, api_settings

from .app import CHUNKING, DATA, INGESTA, PIPELINE
from .graph import UnavailableGraph, open_graph
from .server import serve
from .settings import ServerSettings

Command = Callable[[argparse.Namespace], int]


def _password() -> str | None:
    password = os.environ.get(PASSWORD_VARIABLE) or None
    if password is None and sys.stdin.isatty():
        password = getpass.getpass(f"Neo4j password ({PASSWORD_VARIABLE} is not set; empty = without data): ") or None
    return password


def serve_all(args: argparse.Namespace) -> int:
    settings = ServerSettings(
        ingesta=api_settings(args),
        data=DataSettings(args.neo4j_url, args.neo4j_user, args.neo4j_database or None),
        self_url=ServerSettings.url_for(args.host, args.port),
        neo4j_password=_password(),
    )
    graph = open_graph(settings)
    if isinstance(graph, UnavailableGraph):
        print(f"Warning: {DATA} will answer 503: {graph.reason}", file=sys.stderr)
    else:
        print(f"Neo4j: {settings.data.url} ({settings.data.user})")
    print(f"Memory: {visible_url(settings.ingesta.memory)}")
    print("Docs: " + " | ".join(f"{settings.self_url}{prefix}/docs" for prefix in (INGESTA, DATA, CHUNKING, PIPELINE)))
    serve(settings, graph, args.host, args.port)
    return 0


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prueba-chunking", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    add_organize_command(sub)
    api = add_serve_command(
        sub, "starts the single HTTP server: /ingesta, /data, /chunking and /pipeline (FastAPI + uvicorn)"
    )
    api.add_argument("--neo4j-url", default=NEO4J_URL, help=f"Neo4j server (default {NEO4J_URL})")
    api.add_argument("--neo4j-user", default=NEO4J_USER, help=f"default {NEO4J_USER}")
    api.add_argument(
        "--neo4j-database",
        default=NEO4J_DATABASE,
        help=f"database in the server (default {NEO4J_DATABASE}; empty = its own)",
    )
    api.set_defaults(function=serve_all)
    return parser


def main() -> int:
    args = create_parser().parse_args()
    command: Command = args.function
    return command(args)


if __name__ == "__main__":
    raise SystemExit(main())
