"""Embeddings API routes, one APIRouter per file. To add one: its file here and add it to ROUTERS."""

from fastapi import APIRouter

from .config import router as config
from .experiments import router as experiments
from .health import router as health
from .models import router as models
from .runs import router as runs
from .vectors import router as vectors

ROUTERS: list[APIRouter] = [health, models, config, runs, experiments, vectors]

__all__ = ["ROUTERS"]
