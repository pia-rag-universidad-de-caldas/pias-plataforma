"""Graph adapters: implementations of models.GraphAdapter. The only package that imports neo4j."""

from .neo4j_adapter import Neo4jGraphAdapter

__all__ = ["Neo4jGraphAdapter"]
