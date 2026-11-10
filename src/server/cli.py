"""Project entry point (`prueba-chunking` command, features 020 and 034).

    uv run prueba-chunking                            # the interactive console (same as `prueba-chunking console`):
                                                      # starts Neo4j and Ollama (Docker Compose) and the server if
                                                      # they don't answer (and stops on exit what it started),
                                                      # then any operation of ingesta, data, chunking or pipeline
    NEO4J_PASSWORD=... uv run prueba-chunking serve   # only the server, every module at http://127.0.0.1:8000:
                                                      # every module under its prefix (docs at <prefix>/docs)
    uv run prueba-chunking ask "pregunta"             # one question to a running server (POST /consultas/ask): the
                                                      # answer and its sources (--k, --chat, --url, --sources)
    uv run prueba-chunking migrate-vectors            # once (feature 055): the vectors to their per-model shape
                                                      # (--simulate only counts)

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

from common.logs import LOG_LEVEL, LOG_LEVELS, configure_logging
from data.api import ApiSettings as DataSettings
from data.config import NEO4J_DATABASE, NEO4J_URL, NEO4J_USER, PASSWORD_VARIABLE
from ingesta.adapters import LocalFileAdapter, absolute_path, project_path, visible_url
from ingesta.api import ApiSettings
from ingesta.config import API_HOST, API_PORT, BASE, INGEST, MEMORY_NAME, sqlite_url
from llm.config import OLLAMA_URL, OLLAMA_URL_VARIABLE

from . import ask, migrate
from .app import DATA, MODULE_PREFIXES
from .console import ConsoleSettings, run_console
from .console.settings import GPU, GPUS
from .graph import RECONNECT_EVERY, ReconnectingGraph, UnavailableGraph, open_graph
from .server import serve
from .settings import LOCAL_NAMES, MAX_BODY_BYTES, ServerSettings

Command = Callable[[argparse.Namespace], int]
type Subcommands = argparse._SubParsersAction[argparse.ArgumentParser]

DB_HELP = "URL of the memory database (sqlite:///path, postgresql+psycopg://...); replaces --memory"
COMMANDS = frozenset({"console", "serve", "ask", "migrate-vectors", "-h", "--help"})
INGESTA_OPTIONS = ("base", "ingest", "memory", "db")  # serve options the console passes on to the server it starts
GPU_VARIABLE = "OLLAMA_GPU"


def exposure_warning(host: str) -> str | None:
    """What to say when the server listens beyond this machine, where anyone who reaches it can use it."""
    if host in LOCAL_NAMES:
        return None
    return (
        f"Warning: listening on {host}, and this server has no authentication: anyone who reaches it can read and "
        "change everything. It only answers to the names of this machine and those of --allowed-host."
    )


def _warn_if_exposed(host: str) -> None:
    warning = exposure_warning(host)
    if warning is not None:
        print(warning, file=sys.stderr)


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


def ollama_url(args: argparse.Namespace) -> str:
    """--ollama-url, else the OLLAMA_URL variable, else Ollama's own address on this machine."""
    url: str = args.ollama_url or os.environ.get(OLLAMA_URL_VARIABLE) or OLLAMA_URL
    return url


def serve_all(args: argparse.Namespace) -> int:
    password = _password()
    configure_logging(args.log_level, secrets=(password,) if password else ())
    settings = ServerSettings(
        ingesta=api_settings(args),
        data=DataSettings(args.neo4j_url, args.neo4j_user, args.neo4j_database or None),
        self_url=ServerSettings.url_for(args.host, args.port),
        neo4j_password=password,
        allowed_hosts=tuple(args.allowed_host),
        max_body_bytes=args.max_body_bytes,
        ollama_url=ollama_url(args),
    )
    _warn_if_exposed(args.host)
    graph = open_graph(settings)
    if isinstance(graph, UnavailableGraph):
        print(f"Warning: {DATA} will answer 503: {graph.reason}", file=sys.stderr)
    elif isinstance(graph, ReconnectingGraph):
        print(
            f"Warning: Neo4j doesn't answer yet ({graph.reason}); {DATA} answers 503 and tries again every "
            f"{RECONNECT_EVERY:.0f} s while it is used",
            file=sys.stderr,
        )
    else:
        print(f"Neo4j: {settings.data.url} ({settings.data.user})")
    print(f"Memory: {visible_url(settings.ingesta.memory)}")
    print(f"Ollama: {settings.ollama_url}")
    print("Docs: " + " | ".join(f"{settings.self_url}{prefix}/docs" for prefix in MODULE_PREFIXES))
    serve(settings, graph, args.host, args.port)
    return 0


def console(args: argparse.Namespace) -> int:
    _warn_if_exposed(args.host)
    passed = [(f"--{name}", value) for name in INGESTA_OPTIONS if (value := getattr(args, name))]
    if args.ollama_url:
        passed.append(("--ollama-url", args.ollama_url))
    settings = ConsoleSettings(
        url=ServerSettings.url_for(args.host, args.port),
        neo4j_url=args.neo4j_url,
        neo4j_user=args.neo4j_user,
        neo4j_database=args.neo4j_database,
        neo4j_password=_password(),
        docker=not args.no_docker,
        serve_options=tuple(part for pair in passed for part in pair),
        ollama_url=ollama_url(args),  # the same Ollama the server is given
        gpu=args.gpu,
        keep_docker=args.keep_docker,
    )
    return run_console(settings)


def _gpu() -> str:
    chosen = os.environ.get(GPU_VARIABLE, GPU)
    return chosen if chosen in GPUS else GPU


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
    parser.add_argument(
        "--ollama-url", metavar="URL", help=f"Ollama, for /llm (default ${OLLAMA_URL_VARIABLE} or {OLLAMA_URL})"
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
    menu.add_argument("--no-docker", action="store_true", help="never start Neo4j or Ollama with Docker")
    menu.add_argument(
        "--keep-docker",
        action="store_true",
        help="leave running, on exit, the Docker services the console started (by default it stops them)",
    )
    menu.add_argument(
        "--gpu",
        choices=GPUS,
        default=_gpu(),
        help=f"Ollama's GPU: docker/compose.<gpu>.yaml (default {GPU}, or {GPU_VARIABLE})",
    )
    menu.set_defaults(function=console)
    api = sub.add_parser("serve", help="starts the single HTTP server: every module under its prefix")
    _server_options(api)
    api.add_argument(
        "--allowed-host",
        action="append",
        default=[],
        metavar="NAME",
        help="a name it also answers to, besides this machine's (repeatable): needed to reach it over the network",
    )
    api.add_argument(
        "--max-body-bytes", type=int, default=MAX_BODY_BYTES, help=f"largest body it reads (default {MAX_BODY_BYTES})"
    )
    api.add_argument(
        "--log-level", choices=LOG_LEVELS, default=LOG_LEVEL, help=f"what the logs say (default {LOG_LEVEL})"
    )
    api.set_defaults(function=serve_all)
    ask.add_parser(sub, ServerSettings.url_for(API_HOST, API_PORT))
    migrate.add_parser(sub)
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
