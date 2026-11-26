"""The migrations of feature 055, straight on Neo4j, each one idempotent and with `--simulate` (it only counts). Stop
the server first: the chat may search an index while it is being rebuilt, or an experiment be written while it moves.

`prueba-chunking migrate-vectors` (part a): moves the vectors stored before 055 to their per-model shape
(data.repository.VectorMigration), with the names of embeddings (embeddings.domain). It lives in server because it
needs both: data knows no model and embeddings never touches Neo4j.

`prueba-chunking migrate-experiments` (part b): the chunking experiments to their shape with an EXP_DOCUMENTO per
document, and the leftovers of before feature 043 removed (data.repository.ExperimentMigration; only data).

    NEO4J_PASSWORD=... uv run prueba-chunking migrate-vectors --simulate
    NEO4J_PASSWORD=... uv run prueba-chunking migrate-vectors [--neo4j-url neo4j://localhost:7687]
    NEO4J_PASSWORD=... uv run prueba-chunking migrate-experiments [--simulate]
"""

import argparse
import getpass
import json
import os
import sys
from collections.abc import Callable
from dataclasses import asdict

from data.config import NEO4J_DATABASE, NEO4J_URL, NEO4J_USER, PASSWORD_VARIABLE
from data.models import GraphAdapter, GraphError, Label
from data.repository import (
    ExperimentMigration,
    ExperimentMigrationReport,
    MigrationReport,
    PiaaRepository,
    VectorMigration,
    VectorNaming,
)
from embeddings.config import ACTIVE_CONFIG_ID, DEFAULT_MODEL, MODELS
from embeddings.domain import index_for, property_for


def active_model(graph: GraphAdapter) -> str:
    """The model of embeddings' active configuration (its CONFIG_OFICIAL), or the default one: the model of a vector
    stored without modelo_embedding."""
    node = PiaaRepository(graph).node(Label.CONFIG_OFICIAL, ACTIVE_CONFIG_ID)
    model = None if node is None else node.properties.get("modelo")
    return model if isinstance(model, str) and model in MODELS else DEFAULT_MODEL


def naming(graph: GraphAdapter) -> VectorNaming:
    return VectorNaming(
        property=property_for,
        index=lambda label, property: index_for(label.value, property),
        fallback_model=active_model(graph),
        dimensions={name: spec.dimensions for name, spec in MODELS.items()},
    )


def migrate(graph: GraphAdapter, simulate: bool) -> MigrationReport:
    return VectorMigration(graph, naming(graph)).run(simulate)


def _password() -> str | None:
    password = os.environ.get(PASSWORD_VARIABLE) or None
    if password is None and sys.stdin.isatty():
        password = getpass.getpass("Neo4j password: ") or None
    return password


type Report = MigrationReport | ExperimentMigrationReport


def _migrate_with(args: argparse.Namespace, work: Callable[[GraphAdapter, bool], Report], done: str) -> int:
    """0 when done (or simulated), 1 if Neo4j refused it or isn't there, 2 without a password or driver."""
    password = _password()
    if password is None:
        print(f"Neo4j needs a password: set {PASSWORD_VARIABLE}", file=sys.stderr)
        return 2
    try:
        from data.adapters import Neo4jGraphAdapter  # deferred: it imports the driver (the `data` extra)
    except ImportError:
        print("the Neo4j driver is not installed: uv sync --extra data", file=sys.stderr)
        return 2
    try:
        with Neo4jGraphAdapter(password, args.neo4j_url, args.neo4j_user, args.neo4j_database or None) as graph:
            graph.verify()
            PiaaRepository(graph).ensure_constraints()  # those of 055's labels, if this Neo4j never saw a 055 server
            report = work(graph, args.simulate)
    except GraphError as error:
        print(f"Neo4j: {error}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    if not report.pending:
        print(done, file=sys.stderr)
    return 0


def migrate_vectors(args: argparse.Namespace) -> int:
    return _migrate_with(args, migrate, "Nothing to migrate: the vectors already have the shape of feature 055.")


def migrate_experiments(args: argparse.Namespace) -> int:
    return _migrate_with(
        args,
        lambda graph, simulate: ExperimentMigration(graph).run(simulate),
        "Nothing to migrate: the experiments already have the shape of feature 055.",
    )


def _connection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--simulate", action="store_true", help="only count what it would move")
    parser.add_argument("--neo4j-url", default=NEO4J_URL, help=f"Neo4j server (default {NEO4J_URL})")
    parser.add_argument("--neo4j-user", default=NEO4J_USER, help=f"default {NEO4J_USER}")
    parser.add_argument("--neo4j-database", default=NEO4J_DATABASE, help="database in the server (empty = its own)")


def add_parser(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser(
        "migrate-vectors",
        help="moves the vectors stored before feature 055 to their per-model properties and EXP_EMBED nodes",
    )
    _connection(parser)
    parser.set_defaults(function=migrate_vectors)
    experiments = sub.add_parser(
        "migrate-experiments",
        help="moves the chunking experiments stored before feature 055 to their shape with an EXP_DOCUMENTO per "
        "document, and removes what was left from before feature 043",
    )
    _connection(experiments)
    experiments.set_defaults(function=migrate_experiments)
