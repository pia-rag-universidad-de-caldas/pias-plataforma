"""One APIRouter per file, registered in ROUTERS."""

from fastapi import APIRouter

from . import actions, health, inbox, pipelines, runs

ROUTERS: list[APIRouter] = [health.router, actions.router, pipelines.router, runs.router, inbox.router]
