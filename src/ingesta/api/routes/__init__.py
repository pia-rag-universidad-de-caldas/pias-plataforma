"""API routes, one APIRouter per file. To add one: its file here and add it to ROUTERS."""

from fastapi import APIRouter

from .data import router as data
from .health import router as health
from .ingestion import router as ingestion
from .stats import router as stats

ROUTERS: list[APIRouter] = [health, data, stats, ingestion]

__all__ = ["ROUTERS"]
