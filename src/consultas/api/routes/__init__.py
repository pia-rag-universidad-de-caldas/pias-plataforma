"""consultas API routes, one APIRouter per file. To add one: its file here and add it to ROUTERS."""

from fastapi import APIRouter

from .chats import router as chats
from .config import router as config
from .health import router as health
from .questions import router as questions

ROUTERS: list[APIRouter] = [health, questions, chats, config]

__all__ = ["ROUTERS"]
