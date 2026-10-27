"""Templates: /pipelines CRUD, and reordering their stages (a new order is checked: 422 with the stage and what it
lacks)."""

from dataclasses import replace
from datetime import datetime

from fastapi import APIRouter, status

from pipeline.api.dependencies import Store
from pipeline.api.schemas import MoveBody, NewTemplate, OrderBody, TemplateChange, TemplateView, error
from pipeline.api.templates import all_templates, find
from pipeline.api.views import template_view
from pipeline.domain import BUILTIN, order
from pipeline.models import ConflictError, NotFoundError, RunStore, Template, stages_from_json

router = APIRouter(prefix="/pipelines", tags=["pipelines"])

_INVALID = error(422, "stages that can't run in that order (or malformed)")
_NOT_FOUND = error(404, "there is no template with that id")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _save(store: RunStore, template: Template) -> TemplateView:
    order.check(template.stages)
    template = replace(template, modified=_now(), created=template.created or _now())
    store.save_template(template)
    return template_view(template)


@router.get("")
def list_templates(store: Store) -> list[TemplateView]:
    """The built-in `piaa` first, then the rest by id."""
    return [template_view(t) for t in all_templates(store)]


@router.post("", status_code=status.HTTP_201_CREATED, responses=_INVALID | error(409, "that id already exists"))
def create_template(store: Store, new: NewTemplate) -> TemplateView:
    if store.template(new.id) is not None or new.id in BUILTIN:
        raise ConflictError(f"the template {new.id!r} already exists")
    stages = stages_from_json(list(new.stages))
    return _save(store, Template(new.id, new.name or new.id, new.description, stages))


@router.get("/{id}", responses=_NOT_FOUND)
def read_template(store: Store, id: str) -> TemplateView:
    return template_view(find(store, id))


@router.put("/{id}", responses=_NOT_FOUND | _INVALID)
def replace_template(store: Store, id: str, change: TemplateChange) -> TemplateView:
    """Replaces name, description and stages; the runs already created keep their own copy."""
    current = find(store, id)
    stages = stages_from_json(list(change.stages))
    changed = replace(
        current, name=change.name or current.name, description=change.description or current.description, stages=stages
    )
    return _save(store, changed)


@router.delete(
    "/{id}", status_code=status.HTTP_204_NO_CONTENT, responses=_NOT_FOUND | error(409, "a built-in template")
)
def delete_template(store: Store, id: str) -> None:
    if id in BUILTIN:
        raise ConflictError(f"the template {id!r} is built in: it can be changed, not deleted")
    if not store.delete_template(id):
        raise NotFoundError(f"there is no template {id!r}")


@router.put("/{id}/stages", responses=_NOT_FOUND | _INVALID)
def reorder_stages(store: Store, id: str, body: OrderBody) -> TemplateView:
    """`order`: every top-level stage id, once, in the new order (a cycle's own stages move with /move)."""
    current = find(store, id)
    return _save(store, replace(current, stages=order.reorder(current.stages, body.order)))


@router.post("/{id}/stages/{stage}/move", responses=_NOT_FOUND | _INVALID)
def move_stage(store: Store, id: str, stage: str, body: MoveBody) -> TemplateView:
    """Moves `stage` right `before` or right `after` another stage of its own list (the template's or its cycle's);
    into or out of a cycle, with PUT /pipelines/{id}."""
    current = find(store, id)
    return _save(store, replace(current, stages=order.move(current.stages, stage, body.before, body.after)))
