"""The thread of a pull: its job in the line of WorkQueue, and what it logs (the model and how it ended)."""

import logging
from collections.abc import Callable

from common.logs import brief
from llm.adapters import OllamaClient
from llm.models import ModelsDown

from .registry import PullRegistry
from .work_queue import WorkQueue

LOG = logging.getLogger(__name__)


def launch(
    queue: WorkQueue, registry: PullRegistry, id: str, model: str, open_ollama: Callable[[], OllamaClient]
) -> None:
    """Puts the pull `id` (already registered) in line."""

    def execute() -> None:
        registry.begin(id)
        LOG.info("llm pull %s started: %s", id, model)
        ollama = open_ollama()
        try:
            ollama.pull(model, lambda step: registry.progress(id, step))
        except ModelsDown as error:
            LOG.error("llm pull %s of %s failed: %s", id, model, brief(str(error)))
            registry.finish(id, str(error))
        except Exception as error:  # a bug must not leave it "running" forever (and block the next ones)
            LOG.exception("llm pull %s broke", id)
            registry.finish(id, f"{type(error).__name__}: {error}")
        else:
            LOG.info("llm pull %s finished: %s", id, model)
            registry.finish(id, None)
        finally:
            ollama.close()

    queue.submit(id, execute)
