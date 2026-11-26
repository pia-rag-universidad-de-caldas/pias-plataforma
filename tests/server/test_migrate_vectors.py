"""`prueba-chunking migrate-vectors` (feature 055): data's migration with embeddings' names."""

import argparse
from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import LiteralString

import pytest

from data.models import GraphAdapter, GraphRow, GraphTransaction, Label, Parameters
from embeddings.config import DEFAULT_MODEL
from embeddings.domain import vector_index, vector_property
from embeddings.models import GraphLabel
from server import migrate
from server.cli import create_parser

E5 = "intfloat/multilingual-e5-base"


class _Config(GraphAdapter):
    """Answers only the read of CONFIG_OFICIAL/embeddings, with `rows`."""

    def __init__(self, rows: Sequence[GraphRow]) -> None:
        self._rows = list(rows)

    def verify(self) -> None:
        pass

    def read(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        return self._rows

    def write(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        raise AssertionError("nothing is written")

    def transaction(self) -> AbstractContextManager[GraphTransaction]:
        raise AssertionError("nothing is written")

    def close(self) -> None:
        pass


def test_the_names_are_those_of_embeddings() -> None:
    naming = migrate.naming(_Config([]))
    assert naming.fallback_model == DEFAULT_MODEL
    property = naming.property(DEFAULT_MODEL, 384)
    assert property == vector_property(DEFAULT_MODEL)
    assert naming.index(Label.FRAGMENTOS, property) == vector_index(GraphLabel.FRAGMENTOS, DEFAULT_MODEL).name
    assert naming.index(Label.EXP_EMBED, property) == vector_index(GraphLabel.EXP_EMBED, DEFAULT_MODEL).name


@pytest.mark.parametrize(("stored", "model"), [(E5, E5), ("not/served", DEFAULT_MODEL)])
def test_a_vector_without_model_is_of_the_active_one_if_it_is_served(stored: str, model: str) -> None:
    graph = _Config([{"id": "embeddings", "properties": {"modelo": stored}}])
    assert migrate.active_model(graph) == model


def test_the_command_is_parsed_with_simulate() -> None:
    args: argparse.Namespace = create_parser().parse_args(["migrate-vectors", "--simulate"])
    assert args.simulate and args.function is migrate.migrate_vectors


def test_without_a_password_it_says_so(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert migrate.migrate_vectors(create_parser().parse_args(["migrate-vectors"])) == 2
    assert "NEO4J_PASSWORD" in capsys.readouterr().err


def test_the_experiments_have_their_own_command() -> None:
    """Feature 055 part b: migrate-experiments, with the same options."""
    args: argparse.Namespace = create_parser().parse_args(["migrate-experiments", "--simulate"])
    assert args.simulate and args.function is migrate.migrate_experiments


def test_migrating_the_experiments_without_a_password_says_so(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert migrate.migrate_experiments(create_parser().parse_args(["migrate-experiments"])) == 2
    assert "NEO4J_PASSWORD" in capsys.readouterr().err
