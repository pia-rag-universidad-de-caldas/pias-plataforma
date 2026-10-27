"""The templates the routes see: the stored ones, plus the built-in ones not stored yet (stored when first changed
or used)."""

from pipeline.domain import BUILTIN
from pipeline.models import NotFoundError, RunStore, Template


def all_templates(store: RunStore) -> list[Template]:
    stored = {t.id: t for t in store.templates()}
    return sorted({**BUILTIN, **stored}.values(), key=lambda t: (not t.builtin, t.id))


def find(store: RunStore, id: str) -> Template:
    found = store.template(id) or BUILTIN.get(id)
    if found is None:
        raise NotFoundError(f"there is no template {id!r}")
    return found
