"""The job of an experiment in the line of WorkQueue. It makes HTTP requests to the same server, so it runs in the
queue's thread and never in the event loop."""

import logging
from collections.abc import Callable, Sequence

from chunking.adapters import HttpSession
from chunking.api.work_queue import WorkQueue
from chunking.domain import ExperimentGraph, ExperimentRunner, Resolution
from chunking.models import (
    Chunker,
    DocumentUse,
    ExperimentOutcome,
    ExperimentProgress,
    ExperimentRequest,
    ExperimentResults,
    ExperimentStore,
    SinkError,
)
from common.clock import now
from common.logs import brief

from .registry import ExperimentRegistry

LOG = logging.getLogger(__name__)


def _log_end(id: str, outcome: ExperimentOutcome) -> None:
    for failure in outcome.results.failures:
        LOG.warning("experiment %s: document %s: %s", id, failure.sha256, brief(failure.error))
    done = outcome.progress
    counters = f"done={done.done}/{done.files} errors={done.errors} chunks={done.chunks}"
    if outcome.error:
        LOG.error("experiment %s stopped: %s (%s)", id, brief(outcome.error), counters)
    else:
        LOG.info("experiment %s ended %s: %s", id, "partial" if done.errors else "finished", counters)


def _taken(store: ExperimentStore, request: ExperimentRequest, id: str) -> tuple[Resolution, list[DocumentUse]]:
    """What an experiment of every parsed JSON takes when its turn comes (feature 059): all of them now, but those it
    already chunked (a resume) stay as they are."""
    return ExperimentRunner.pending(store, request, store.uses(id))


def launch(
    queue: WorkQueue,
    registry: ExperimentRegistry,
    id: str,
    open_session: Callable[[], HttpSession],
    chunker: Chunker,
    request: ExperimentRequest,
    resolution: Resolution | None,
    kept: Sequence[DocumentUse] = (),
) -> None:
    """Puts the experiment (already registered and stored) in line; one HTTP session for all of it. `kept`: on a
    resume, what it already chunked. `resolution` None (feature 059, `all`): the documents are taken when its turn
    comes, skipping those it already chunked."""

    def execute() -> None:
        try:
            with open_session() as session:
                store = session.experiments
                at = now()
                try:
                    planned, done = (resolution, kept) if resolution is not None else _taken(store, request, id)
                except SinkError as down:  # data down when its turn came: it ends failed, having chunked nothing
                    LOG.error("experiment %s could not take its documents: %s", id, brief(str(down)))
                    empty = ExperimentResults(0, 0, 0, 0, 0, None, 0.0, [], [])
                    store.save(ExperimentGraph.finish(id, empty, ExperimentProgress(), str(down), now()))
                    return
                files = len(planned.sha256s) + len(done) if resolution is None else None
                store.save(ExperimentGraph.started(id, at, files))
                registry.begin(id, at)
                LOG.info("experiment %s started", id)
                try:
                    outcome = ExperimentRunner.run(
                        store, chunker, id, request, planned, lambda progress: registry.progress(id, progress), done
                    )
                except Exception as error:  # a bug must not leave the experiment "running"
                    empty = ExperimentResults(0, 0, 0, len(planned.unparsed), 0, None, 0.0, [], [])
                    outcome = ExperimentOutcome(empty, ExperimentProgress(), f"{type(error).__name__}: {error}")
                    LOG.exception("experiment %s broke", id)
                _log_end(id, outcome)
                store.save(ExperimentGraph.finish(id, outcome.results, outcome.progress, outcome.error, now()))
        except Exception:  # data down at the very end: the experiment shows as interrupted, and this says why
            LOG.exception("experiment %s: its end could not be stored", id)
        finally:
            registry.done(id)

    queue.submit(id, execute)
