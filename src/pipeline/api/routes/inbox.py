"""The actors: what waits for them (/inbox) and their callback_url (/actors)."""

from fastapi import APIRouter

from pipeline.api.dependencies import Actors, Runner, Store
from pipeline.api.executor import item_json
from pipeline.api.schemas import ActorBody, ActorView
from pipeline.models import Actor, JsonObject, RunStatus

router = APIRouter(tags=["actors"])


@router.get("/inbox")
def inbox(store: Store, runner: Runner, actor: str | None = None) -> list[JsonObject]:
    """The stages waiting for `actor` (every actor if not given), oldest first: run, stage, iteration, the
    experiment to look at in chunking, the batch, the artifacts and the route to answer to."""
    items = [runner.inbox_item(r) for r in store.runs() if r.status == RunStatus.WAITING]
    found = [i for i in items if i is not None and (actor is None or i.actor == actor)]
    return [item_json(i) for i in sorted(found, key=lambda i: i.since)]


@router.get("/actors")
def list_actors(actors: Actors) -> list[ActorView]:
    return [ActorView(a.name, a.callback_url) for a in actors.all()]


@router.put("/actors/{name}")
def put_actor(actors: Actors, name: str, body: ActorBody) -> ActorView:
    """Registers the actor; with `callback_url`, it gets a POST (what /inbox lists) when a stage starts waiting for
    it. Kept in memory: it is configuration of this server."""
    actor = actors.put(Actor(name, body.callback_url or None))
    return ActorView(actor.name, actor.callback_url)
