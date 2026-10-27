"""Project entry point (`prueba-chunking` command, features 020 and 034).

    uv run prueba-chunking                            # the interactive console (same as `prueba-chunking console`):
                                                      # starts Neo4j (Docker) and the server if they don't answer,
                                                      # then any operation of ingesta, data, chunking or pipeline
    NEO4J_PASSWORD=... uv run prueba-chunking serve   # only the server, every module at http://127.0.0.1:8000:
                                                      # /ingesta, /data, /chunking, /pipeline (docs at <prefix>/docs)

The ingestion runs from the API (POST /ingesta/runs, also from the console). The Neo4j password is read from the
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
from ingesta.adapters import LocalFileAdapter, absolute_path, project_path, visible_url
from ingesta.api import ApiSettings
from ingesta.config import API_HOST, API_PORT, BASE, INGEST, MEMORY_NAME, sqlite_url

from .app import CHUNKING, DATA, INGESTA, PIPELINE
from .console import ConsoleSettings, run_console
from .graph import UnavailableGraph, open_graph
from .server import serve
from .settings import ServerSettings

Command = Callable[[argparse.Namespace], int]
type Subcommands = argparse._SubParsersAction[argparse.ArgumentParser]

DB_HELP = "URL of the memory database (sqlite:///path, postgresql+psycopg://...); replaces --memory"
COMMANDS = frozenset({"console", "serve", "-h", "--help"})
INGESTA_OPTIONS = ("base", "ingest", "memory", "db")  # serve options the console passes on to the server it starts


def _password() -> str | None:
    password = os.environ.get(PASSWORD_VARIABLE) or None
    if password is None and sys.stdin.isatty():
        password = getpass.getpass(f"Neo4j password ({PASSWORD_VARIABLE} is not set; empty = without data): ") or None
    return password


def _memory_url(args: argparse.Namespace, ingest: LocalFileAdapter) -> str:
    """The memory URL: --db, or the SQLite of --memory, or the one in the ingesta folder."""
    url: str = args.db or sqlite_url(absolute_path(args.memory) if args.memory else ingest.absolute(MEMORY_NAME))
    return url


def api_settings(args: argparse.Namespace) -> ApiSettings:
    """The ingesta settings from the `serve` options."""
    base = LocalFileAdapter(args.base or project_path(BASE))
    ingest = LocalFileAdapter(args.ingest or project_path(INGEST))
    return ApiSettings(base.absolute(), ingest.absolute(), _memory_url(args, ingest))


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


def console(args: argparse.Namespace) -> int:
    passed = [(f"--{name}", value) for name in INGESTA_OPTIONS if (value := getattr(args, name))]
    settings = ConsoleSettings(
        url=ServerSettings.url_for(args.host, args.port),
        neo4j_url=args.neo4j_url,
        neo4j_user=args.neo4j_user,
        neo4j_database=args.neo4j_database,
        neo4j_password=_password(),
        docker=not args.no_docker,
        serve_options=tuple(part for pair in passed for part in pair),
    )
    return run_console(settings)


def _server_options(parser: argparse.ArgumentParser) -> None:
    """Where the server listens, its ingesta folders and its Neo4j (serve and console)."""
    parser.add_argument("--host", default=API_HOST, help=f"interface to listen on (default {API_HOST})")
    parser.add_argument("--port", type=int, default=API_PORT, help=f"default {API_PORT}")
    parser.add_argument("--base", help=f"input folder (default {BASE})")
    parser.add_argument("--ingest", help=f"output folder (default {INGEST})")
    parser.add_argument("--memory", help=f"SQLite memory file (default {INGEST}/{MEMORY_NAME})")
    parser.add_argument("--db", metavar="URL", help=DB_HELP)
    parser.add_argument("--neo4j-url", default=NEO4J_URL, help=f"Neo4j server (default {NEO4J_URL})")
    parser.add_argument("--neo4j-user", default=NEO4J_USER, help=f"default {NEO4J_USER}")
    parser.add_argument(
        "--neo4j-database",
        default=NEO4J_DATABASE,
        help=f"database in the server (default {NEO4J_DATABASE}; empty = its own)",
    )


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prueba-chunking", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub: Subcommands = parser.add_subparsers(dest="command")
    menu = sub.add_parser(
        "console",
        help="interactive console (default): starts Neo4j if missing and its own server, alive while the console is",
    )
    _server_options(menu)
    menu.add_argument("--no-docker", action="store_true", help="never start Neo4j with Docker")
    menu.set_defaults(function=console)
    api = sub.add_parser("serve", help="starts the single HTTP server: /ingesta, /data, /chunking and /pipeline")
    _server_options(api)
    api.set_defaults(function=serve_all)
    return parser


def main() -> int:
    arguments = sys.argv[1:]
    if not arguments or arguments[0] not in COMMANDS:  # no command: the console, with the options given
        arguments = ["console", *arguments]
    args = create_parser().parse_args(arguments)
    command: Command = args.function
    return command(args)


if __name__ == "__main__":
    raise SystemExit(main())
