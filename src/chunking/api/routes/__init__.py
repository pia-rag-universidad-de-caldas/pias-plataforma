"""Chunking API routes, one APIRouter per file. To add one: its file here and add it to ROUTERS."""

from fastapi import APIRouter

from .documents import router as documents
from .experiments import router as experiments
from .health import router as health
from .runs import router as runs
from .scores import router as scores

ROUTERS: list[APIRouter] = [health, runs, documents, experiments, scores]

__all__ = ["ROUTERS"]
