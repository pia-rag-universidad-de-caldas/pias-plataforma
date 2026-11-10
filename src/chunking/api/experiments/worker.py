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


def launch(
    queue: WorkQueue,
    registry: ExperimentRegistry,
    id: str,
    open_session: Callable[[], HttpSession],
    chunker: Chunker,
    request: ExperimentRequest,
    resolution: Resolution,
    kept: Sequence[DocumentUse] = (),
) -> None:
    """Puts the experiment (already registered and stored) in line; one HTTP session for all of it. `kept`: on a
    resume, what it already chunked."""

    def execute() -> None:
        try:
            with open_session() as session:
                store = session.experiments
                at = now()
                store.save(ExperimentGraph.started(id, at))
                registry.begin(id, at)
                LOG.info("experiment %s started", id)
                try:
                    outcome = ExperimentRunner.run(
                        store, chunker, id, request, resolution, lambda progress: registry.progress(id, progress), kept
                    )
                except Exception as error:  # a bug must not leave the experiment "running"
                    empty = ExperimentResults(0, 0, 0, len(resolution.unparsed), 0, None, 0.0, [], [])
                    outcome = ExperimentOutcome(empty, ExperimentProgress(), f"{type(error).__name__}: {error}")
                    LOG.exception("experiment %s broke", id)
                _log_end(id, outcome)
                store.save(ExperimentGraph.finish(id, outcome.results, outcome.progress, outcome.error, now()))
        except Exception:  # data down at the very end: the experiment shows as interrupted, and this says why
            LOG.exception("experiment %s: its end could not be stored", id)
        finally:
            registry.done(id)

    queue.submit(id, execute)
