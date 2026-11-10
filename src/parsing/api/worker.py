"""The thread of a parsing run: its job in the line of WorkQueue, and what it stores and logs.

A run makes HTTP requests to the same server (data), so it never runs in the event loop: it gets the queue's thread,
and the server keeps answering (those requests included). One at a time: the others wait in WorkQueue.
"""

import logging
import time
from collections.abc import Callable

from common.clock import now
from common.logs import brief
from parsing.adapters import HttpSession
from parsing.domain import ParsingRunner
from parsing.models import DocumentResult, DocumentState, Parser, ParsingRequest, RunOutcome, RunProgress

from .history import save
from .registry import RunRegistry
from .work_queue import WorkQueue

LOG = logging.getLogger(__name__)


def launch(
    queue: WorkQueue,
    registry: RunRegistry,
    id: str,
    open_session: Callable[[], HttpSession],
    parser: Parser,
    request: ParsingRequest,
) -> None:
    """Puts the run `id` (already registered) in line; one HTTP session for the whole run."""

    def record() -> None:
        current = registry.get(id)
        if current is not None:
            with open_session() as session:
                save(session.runs, current)

    def decided(result: DocumentResult, progress: RunProgress) -> None:
        registry.document(id, result, progress)
        if result.state is DocumentState.ERROR:
            LOG.warning("parsing run %s: document %s failed: %s", id, result.sha256, brief(result.error or "?"))

    def execute() -> None:
        current = registry.get(id)
        if current is None:
            return
        registry.begin(id)
        LOG.info("parsing run %s started: %d documents, fingerprint %s", id, len(request.sha256s), current.fingerprint)
        record()
        try:
            with open_session() as session:
                outcome = ParsingRunner.run(
                    request, session.raws, session.parsed, parser, current.fingerprint, now, time.monotonic, decided
                )
        except Exception as error:  # a bug must not leave the run "running" forever (and block the next ones)
            ran = registry.get(id)
            outcome = RunOutcome(ran.progress if ran else RunProgress(), f"{type(error).__name__}: {error}")
            LOG.exception("parsing run %s broke", id)
        registry.finish(id, outcome)
        done = outcome.progress
        counters = f"parsed={done.parsed} partial={done.partial} errors={done.errors} skipped={done.skipped}"
        if outcome.error:
            LOG.error("parsing run %s stopped: %s (%s)", id, brief(outcome.error), counters)
        else:
            LOG.info("parsing run %s finished: %s missing=%d", id, counters, done.missing)
        record()
        registry.on_done()

    record()
    queue.submit(id, execute)
