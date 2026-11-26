"""GET /targets: where a question can be asked (feature 060), for the selector of each panel of a comparison."""

from fastapi import APIRouter

from consultas.api.dependencies import Modules
from consultas.api.responses import DOWN, REFUSED
from consultas.domain import targets
from consultas.models import Targets

router = APIRouter(tags=["targets"])


@router.get("/targets", responses=DOWN | REFUSED)
def list_targets(modules: Modules) -> Targets:
    """`official`: each embeddings model with official vectors (`documents_done` > 0), and the active one always, with
    how many official documents have them (GET /data/progress/embeddings); ask it with `against: {embeddings_model}`.
    `experiments`: the finished embeddings experiments with what their chunking experiment chunked with
    (`chunking_name` and `chunking` null if it was deleted); ask one with `against: {embeddings_experiment}`. Reads
    every experiment: 503 if embeddings, data or chunking doesn't answer, saying which."""
    return targets(modules.catalog, modules.progress, modules.chunking)
