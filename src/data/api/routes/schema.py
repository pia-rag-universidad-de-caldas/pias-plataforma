"""GET /schema: the node labels and relationships the PIAA graph allows."""

from fastapi import APIRouter

from data.api.schemas import Schema
from data.models import Label
from data.schema import RELATIONSHIPS

router = APIRouter(tags=["schema"])


@router.get("/schema")
def schema() -> Schema:
    return Schema(labels=list(Label), relationships=list(RELATIONSHIPS))
