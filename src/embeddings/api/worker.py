"""The thread of a run or an experiment: its job in the line of WorkQueue, and what it stores and logs.

It makes HTTP requests to the same server (data), so it never runs in the event loop: it gets the queue's thread, and
the server keeps answering (those requests included). It logs ids and counts, never the text of a document.
"""

import logging
import threading
from collections.abc import Callable

from common.logs import brief
from embeddings.adapters import HttpSession
from embeddings.domain import RunEvents
from embeddings.models import DocumentFailure, RunProgress, UpstreamDown

from .history import save
from .registry import RunRegistry
from .work_queue import WorkQueue

LOG = logging.getLogger(__name__)

type Work = Callable[[HttpSession, RunEvents], RunProgress]  # the domain's run, over an open session


def launch(
    queue: WorkQueue, registry: RunRegistry, id: str, open_session: Callable[[], HttpSession], work: Work
) -> None:
    """Puts `id` (already registered) in line; one HTTP session for all of it."""

    def record() -> None:
        current = registry.get(id)
        if current is not None:
            with open_session() as session:
                save(session.runs, current)

    def failed(failure: DocumentFailure) -> None:
        LOG.warning("embeddings %s: document %s failed: %s", id, failure.sha256, brief(failure.error))
        registry.failure(id, failure)

    def execute() -> None:
        current = registry.get(id)
        if current is None:
            return
        registry.begin(id)
        LOG.info("embeddings %s %s started: %s", current.kind.value, id, current.config.model)
        record()
        halted = threading.Event()  # the domain stopped because it was asked to (feature 056)

        def stop() -> bool:
            if registry.stopping(id):
                halted.set()
                return True
            return False

        events = RunEvents(
            lambda p: registry.progress(id, p),
            failed,
            lambda sha256: registry.embedded(id, sha256),
            lambda sha256s: registry.listed(id, sha256s),
            stop,
        )
        try:
            with open_session() as session:
                progress = work(session, events)
        except UpstreamDown as error:  # the machine, not a document: nothing more is written
            LOG.error("embeddings %s stopped: %s", id, brief(str(error)))
            registry.finish(id, None, str(error))
        except Exception as error:  # a bug must not leave it "running" forever (and block the next ones)
            LOG.exception("embeddings %s broke", id)
            registry.finish(id, None, f"{type(error).__name__}: {error}")
        else:
            counters = f"embedded={progress.embedded} unchanged={progress.unchanged} errors={progress.errors}"
            ended = "cancelled" if halted.is_set() else "finished"
            LOG.info("embeddings %s %s: %s chunks=%d", id, ended, counters, progress.chunks)
            registry.finish(id, progress, None, halted.is_set())
        try:
            record()
        finally:
            registry.on_done()

    record()
    queue.submit(id, execute)
