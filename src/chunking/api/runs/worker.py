"""The job of a run in the line of WorkQueue, and what it stores and logs. It makes HTTP requests to the same server
(data), so it runs in the queue's thread and never in the event loop. It is stored when asked for, when its turn comes
and when it ends: if data doesn't answer for the record, the run goes on.

A run without a frozen list takes what is missing with its configuration when its turn comes, not when it was asked
for: the line runs one job at a time, so two runs of "page 1" in line take two different batches."""

import logging
from collections.abc import Callable

from chunking.adapters import HttpSession
from chunking.api.work_queue import WorkQueue
from chunking.domain import RunGraph, RunRunner
from chunking.models import (
    Chunker,
    ChunkingRun,
    DocumentError,
    DocumentFailure,
    RunOutcome,
    RunProgress,
    SinkError,
)
from common.clock import now
from common.logs import brief

from .registry import RunRegistry

LOG = logging.getLogger(__name__)


def record(registry: RunRegistry, id: str, open_session: Callable[[], HttpSession]) -> None:
    current = registry.get(id)
    if current is None:
        return
    try:
        with open_session() as session:
            session.runs.save(RunGraph.record(current))
    except (SinkError, DocumentError) as error:
        LOG.warning("the run %s wasn't stored: %s", id, error)


def launch(
    queue: WorkQueue,
    registry: RunRegistry,
    run: ChunkingRun,
    open_session: Callable[[], HttpSession],
    chunker: Chunker,
) -> None:
    """Puts `run` (already registered, new or resumed) in line; one HTTP session for all of it."""
    id = run.id

    def failed(failure: DocumentFailure) -> None:
        registry.failure(id, failure)
        LOG.warning("run %s: document %s failed: %s", id, failure.sha256, brief(failure.error))

    def execute() -> None:
        try:
            with open_session() as session:
                sha256s = run.sha256s
                if not run.frozen:
                    sha256s = session.documents.missing(run.parameters.fingerprint, run.page, run.per_page)
                registry.begin(id, sha256s)
                LOG.info("run %s started: %d documents", id, len(sha256s))
                record(registry, id, open_session)
                outcome = RunRunner.run(
                    session.documents,
                    chunker,
                    sha256s,
                    run.parameters,
                    run.experiment,
                    now,
                    on_progress=lambda progress: registry.progress(id, progress),
                    on_failure=failed,
                )
        except Exception as error:  # data down before it started, or a bug: never "running" forever
            current = registry.get(id)
            progress = current.progress if current else RunProgress()
            failures = current.failures if current else []
            text = str(error) if isinstance(error, SinkError) else f"{type(error).__name__}: {error}"
            outcome = RunOutcome(progress, current.chunked if current else [], failures, text)
            if not isinstance(error, SinkError):
                LOG.exception("run %s broke", id)
        registry.finish(id, outcome)
        done = outcome.progress
        counters = f"chunked={done.chunked} skipped={done.skipped} unparsed={done.unparsed} errors={done.errors}"
        if outcome.error:
            LOG.error("run %s stopped: %s (%s)", id, brief(outcome.error), counters)
        else:
            LOG.info("run %s ended %s: %s chunks=%d", id, outcome.status.value, counters, done.chunks)
        record(registry, id, open_session)
        registry.on_done()

    record(registry, id, open_session)
    queue.submit(id, execute)
