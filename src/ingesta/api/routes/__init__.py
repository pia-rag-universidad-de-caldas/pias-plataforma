"""API routes, one APIRouter per file. To add one: its file here and add it to ROUTERS."""

from fastapi import APIRouter

from .data import router as data
from .health import router as health
from .ingestion import router as ingestion
from .stats import router as stats
from .uploads import router as uploads

ROUTERS: list[APIRouter] = [health, data, stats, ingestion, uploads]

__all__ = ["ROUTERS"]
