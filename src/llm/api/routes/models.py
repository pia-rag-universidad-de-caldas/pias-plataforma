"""The models: GET /models (the admitted ones and what Ollama has), POST /models/pull (a download in line, one at a
time: follow it with GET /models/pulls/{id} or GET /processes), GET /models/pulls and DELETE /models/{name}."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status

from common.clock import now
from llm.api.dependencies import Config, Ollama, Queue, Registry, Settings
from llm.api.responses import DATA_DOWN, INVALID, OLLAMA_DOWN, error
from llm.api.schemas import AdmittedModel, InstalledView, ModelsView, NewPull
from llm.api.work_queue import LINE_FULL
from llm.api.worker import launch
from llm.config import DEFAULT_MODEL, MODELS
from llm.domain import admitted, resolve, same_model
from llm.models import ModelPull, PullStatus

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", responses=OLLAMA_DOWN)
def list_models(ollama: Ollama) -> ModelsView:
    """The models the project admits (whether Ollama has each one, and which is the default) and every model Ollama
    has downloaded. 503 if Ollama doesn't answer."""
    installed = ollama.installed()
    return ModelsView(
        [
            AdmittedModel(
                name,
                spec.context,
                spec.vision,
                any(same_model(name, m.name) for m in installed),
                name == DEFAULT_MODEL,
            )
            for name, spec in MODELS.items()
        ],
        [InstalledView(m.name, m.size, m.family, m.modified) for m in installed],
    )


@router.post(
    "/pull",
    status_code=status.HTTP_202_ACCEPTED,
    responses=OLLAMA_DOWN | INVALID | error(409, "the line of pulls is full"),
)
def pull_model(settings: Settings, registry: Registry, queue: Queue, ollama: Ollama, body: NewPull) -> ModelPull:
    """Downloads an admitted model in Ollama, in the background: answers at once (`queued` if another one downloads).
    Pulling one Ollama already has brings it up to date."""
    admitted(body.name)
    if queue.full:
        raise HTTPException(status.HTTP_409_CONFLICT, LINE_FULL)
    ollama.version()  # 503 now, not a failed pull later, if Ollama doesn't answer
    pull = ModelPull(uuid4().hex[:12], body.name, PullStatus.QUEUED, now())
    registry.add(pull)
    launch(queue, registry, pull.id, body.name, settings.ollama)
    return registry.get(pull.id) or pull


@router.get("/pulls")
def list_pulls(registry: Registry) -> list[ModelPull]:
    """The pulls of this server session, newest first (they are not stored: Ollama keeps the models)."""
    return registry.all()


@router.get("/pulls/{id}", responses=error(404, "no pull with that id in this session"))
def read_pull(registry: Registry, id: str) -> ModelPull:
    found = registry.get(id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no pull with id {id!r} in this session")
    return found


@router.delete(
    "/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=OLLAMA_DOWN
    | DATA_DOWN
    | INVALID
    | error(404, "Ollama doesn't have it")
    | error(409, "it is the model of the active configuration"),
)
def delete_model(ollama: Ollama, config: Config, name: str) -> Response:
    """Removes an admitted model from Ollama; never the one of the active configuration (change it first)."""
    admitted(name)
    if same_model(resolve(config).model, name):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{name} is the model of the active configuration")
    if not ollama.delete(name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Ollama doesn't have {name}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
