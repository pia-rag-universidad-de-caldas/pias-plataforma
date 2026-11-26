"""Neo4jGraphAdapter: a server that isn't there needs no server; the rest, a real Neo4j (omitted without one)."""

import pytest

from data.models import GraphAdapter, GraphError


def adapter(url: str) -> GraphAdapter:
    pytest.importorskip("neo4j")
    from data.adapters import Neo4jGraphAdapter  # it needs the driver (the data extra)

    return Neo4jGraphAdapter("password", url)


def test_a_url_that_makes_no_sense_is_a_graph_error() -> None:
    with pytest.raises(GraphError, match="could not create the connection"):
        adapter("nada://localhost")


def test_a_server_that_isnt_there_is_a_graph_error() -> None:
    with adapter("neo4j://localhost:1") as graph, pytest.raises(GraphError, match="not answering"):
        graph.verify()


@pytest.mark.neo4j
def test_a_server_that_answers_passes_the_check(real_graph: GraphAdapter) -> None:
    real_graph.verify()
    assert real_graph.read("RETURN 1 AS one") == [{"one": 1}]


@pytest.mark.neo4j
def test_what_is_written_can_be_read_with_its_parameters(real_graph: GraphAdapter, test_prefix: str) -> None:
    real_graph.write("CREATE (:PIAA {id: $id, valor: 3})", {"id": test_prefix})
    assert real_graph.read("MATCH (n:PIAA {id: $id}) RETURN n.valor AS valor", {"id": test_prefix}) == [{"valor": 3}]


@pytest.mark.neo4j
def test_a_transaction_is_confirmed_when_its_block_ends(real_graph: GraphAdapter, test_prefix: str) -> None:
    with real_graph.transaction() as tx:
        tx.run("CREATE (:PIAA {id: $id})", {"id": test_prefix})
    assert len(real_graph.read("MATCH (n:PIAA {id: $id}) RETURN n.id AS id", {"id": test_prefix})) == 1


@pytest.mark.neo4j
def test_an_exception_undoes_the_whole_transaction(real_graph: GraphAdapter, test_prefix: str) -> None:
    with pytest.raises(ValueError, match="stop"), real_graph.transaction() as tx:
        tx.run("CREATE (:PIAA {id: $id})", {"id": test_prefix})
        raise ValueError("stop")
    assert real_graph.read("MATCH (n:PIAA {id: $id}) RETURN n.id AS id", {"id": test_prefix}) == []


@pytest.mark.neo4j
def test_a_query_neo4j_doesnt_understand_is_a_graph_error(real_graph: GraphAdapter) -> None:
    with pytest.raises(GraphError, match="query rejected"):
        real_graph.read("THIS IS NOT CYPHER")


@pytest.mark.neo4j
def test_a_rejected_query_inside_a_transaction_is_a_graph_error(real_graph: GraphAdapter) -> None:
    with pytest.raises(GraphError), real_graph.transaction() as tx:
        tx.run("THIS IS NOT CYPHER")
