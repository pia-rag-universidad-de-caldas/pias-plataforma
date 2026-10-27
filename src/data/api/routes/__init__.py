"""Graph API routes, one APIRouter per file. To add one: its file here and add it to ROUTERS."""

from fastapi import APIRouter

from .batch import router as batch
from .health import router as health
from .nodes import router as nodes
from .relationships import router as relationships
from .schema import router as schema

ROUTERS: list[APIRouter] = [health, schema, nodes, relationships, batch]

__all__ = ["ROUTERS"]
