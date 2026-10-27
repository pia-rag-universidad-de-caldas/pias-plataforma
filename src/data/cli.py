"""Entry point of data (`prueba-chunking-data` command; requires `uv sync --extra data`).

    NEO4J_PASSWORD=... uv run prueba-chunking-data serve   # graph API at http://127.0.0.1:8001 (/docs)

The Neo4j password is read from the NEO4J_PASSWORD environment variable; if missing and there is a console, it is
prompted for without echo.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable

from data.adapters import Neo4jGraphAdapter, environment_variable
from data.api import ApiSettings, serve
from data.config import API_HOST, API_PORT, NEO4J_DATABASE, NEO4J_URL, NEO4J_USER, PASSWORD_VARIABLE
from data.models import GraphError
from data.repository import PiaaRepository

Command = Callable[[argparse.Namespace], int]


def _password() -> str | None:
    password = environment_variable(PASSWORD_VARIABLE)
    if password is None and sys.stdin.isatty():
        password = getpass.getpass(f"Neo4j password ({PASSWORD_VARIABLE} is not set): ") or None
    return password


def serve_api(args: argparse.Namespace) -> int:
    password = _password()
    if password is None:
        print(
            f"Error: the Neo4j password is missing from the {PASSWORD_VARIABLE} environment variable", file=sys.stderr
        )
        return 1
    database: str | None = args.database or None
    try:
        graph = Neo4jGraphAdapter(password, args.url, args.user, database)
    except GraphError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    try:
        graph.verify()
        PiaaRepository(graph).ensure_constraints()
    except GraphError as error:
        graph.close()
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Neo4j: {args.url} ({args.user}) | docs: http://{args.host}:{args.port}/docs")
    serve(ApiSettings(args.url, args.user, database), graph, args.host, args.port)
    return 0


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prueba-chunking-data", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    api = sub.add_parser("serve", help="starts the PIAA graph HTTP API (node and relationship CRUD)")
    api.add_argument("--host", default=API_HOST, help=f"interface to listen on (default {API_HOST})")
    api.add_argument("--port", type=int, default=API_PORT, help=f"default {API_PORT}")
    api.add_argument("--url", default=NEO4J_URL, help=f"Neo4j server (default {NEO4J_URL})")
    api.add_argument("--user", default=NEO4J_USER, help=f"default {NEO4J_USER}")
    api.add_argument(
        "--database", default=NEO4J_DATABASE, help=f"database in the server (default {NEO4J_DATABASE}; empty = its own)"
    )
    api.set_defaults(function=serve_api)
    return parser


def main() -> int:
    args = create_parser().parse_args()
    command: Command = args.function
    return command(args)


if __name__ == "__main__":
    raise SystemExit(main())
