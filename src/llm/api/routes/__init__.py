"""llm API routes, one APIRouter per file. To add one: its file here and add it to ROUTERS."""

from fastapi import APIRouter

from .chat import router as chat
from .config import router as config
from .health import router as health
from .models import router as models

ROUTERS: list[APIRouter] = [health, models, config, chat]

__all__ = ["ROUTERS"]
