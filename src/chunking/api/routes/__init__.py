"""Chunking API routes, one APIRouter per file. To add one: its file here and add it to ROUTERS."""

from fastapi import APIRouter

from .config import router as config
from .experiments import router as experiments
from .health import router as health
from .runs import router as runs

ROUTERS: list[APIRouter] = [health, runs, experiments, config]

__all__ = ["ROUTERS"]
