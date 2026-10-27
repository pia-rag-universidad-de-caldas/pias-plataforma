"""Executor: drives the runs of this server with the Engine (domain) and the adapters.

Each task goes to the FIFO queue of its module (ingesta, chunking, data), one worker thread per queue: chunking runs
one experiment at a time, so its stages wait their turn in line. A waiting run occupies no thread: it is only in the
graph until its actor answers (decide/complete), which may come after a restart. A run that was in a task when the
server stopped is shown `interrupted` (stored `running`/`queued`, but not in this executor) until resumed.

Every change of a run is load → Engine → save under one lock, so an answer and a worker never overwrite each other;
a worker that finds its run changed meanwhile (cancelled...) drops what it did.
"""

import logging
import queue
import threading
from collections.abc import Callable
from datetime import datetime

from pipeline.domain import Engine
from pipeline.models import (
    Completion,
    ConflictError,
    Decision,
    EventRequest,
    InboxItem,
    JsonObject,
    Modules,
    NotFoundError,
    Notifier,
    PipelineError,
    PipelineRun,
    RunStatus,
    RunStore,
    StageKind,
    json_list,
)

from .actor_registry import ActorRegistry

LOG = logging.getLogger(__name__)
QUEUES = ("ingesta", "chunking", "data")
PIPELINE = "pipeline"  # the actor of the events the pipeline itself records


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def item_json(item: InboxItem) -> JsonObject:
    return {
        "run": item.run,
        "name": item.name,
        "stage": item.stage,
        "step": item.step,
        "actor": item.actor,
        "since": item.since,
        "iteration": item.iteration,
        "exhausted": item.exhausted,
        "experiment": item.experiment,
        "batch": json_list(item.batch),
        "artifacts": item.artifacts,
        "answer": item.answer,
    }


class Executor:
    def __init__(
        self,
        store: RunStore,
        modules: Modules,
        notifier: Notifier,
        actors: ActorRegistry,
        answer_route: Callable[[PipelineRun], str],
    ) -> None:
        self._store = store
        self.modules = modules
        self._notifier = notifier
        self._actors = actors
        self._answer_route = answer_route
        self._lock = threading.RLock()
        self._active: set[str] = set()  # runs in a queue or in a worker
        self._queues: dict[str, queue.Queue[str]] = {name: queue.Queue() for name in QUEUES}
        self._workers: list[threading.Thread] = []

    # --- reading ---

    def status(self, run: PipelineRun) -> RunStatus:
        """The status to show: a queued/running run this executor isn't processing was interrupted."""
        with self._lock:
            processing = run.id in self._active
        if run.status in (RunStatus.QUEUED, RunStatus.RUNNING) and not processing:
            return RunStatus.INTERRUPTED
        return run.status

    def inbox_item(self, run: PipelineRun) -> InboxItem | None:
        return Engine.inbox_item(run, self._answer_route(run))

    def _load(self, id: str) -> PipelineRun:
        run = self._store.run(id)
        if run is None:
            raise NotFoundError(f"there is no run {id}")
        return run

    # --- driving ---

    def _start_workers(self) -> None:
        if not self._workers:
            for name in QUEUES:
                worker = threading.Thread(target=self._work, args=(name,), name=f"pipeline-{name}", daemon=True)
                worker.start()
                self._workers.append(worker)

    def _continue(self, run: PipelineRun) -> PipelineRun:
        """Under the lock: saves the run and sends its next task to its queue, or leaves it waiting or done."""
        step = Engine.next(run) if run.status == RunStatus.RUNNING else None
        if step is not None and step.kind == StageKind.TASK:
            self._active.add(run.id)
            self._store.save_run(run)
            self._start_workers()
            self._queues[step.action.module or "data"].put(run.id)
            return run
        if step is not None and step.kind == StageKind.WAIT:
            run = Engine.wait(run, now())
        self._active.discard(run.id)
        self._store.save_run(run)
        return run

    def _notify(self, run: PipelineRun) -> None:
        """Tells the actor a waiting run waits for it (outside the lock: it is another process); a failure is
        recorded as an event and the stage stays in the inbox."""
        item = self.inbox_item(run)
        if item is None:
            return
        error = self._notifier.notify(self._actors.get(item.actor), item_json(item))
        if error is None:
            return
        with self._lock:
            fresh = self._store.run(run.id)
            if fresh is not None:
                event = EventRequest(PIPELINE, "notify_failed", {"actor": item.actor, "error": error})
                self._store.save_run(Engine.event(fresh, event, now()))

    def _after(self, run: PipelineRun) -> PipelineRun:
        if run.status == RunStatus.WAITING:
            self._notify(run)
        return run

    def launch(self, run: PipelineRun) -> PipelineRun:
        """Stores a new (queued) run and starts it."""
        with self._lock:
            if self._store.template(run.template.id) is None:  # the built-in one is only stored when first used
                self._store.save_template(run.template)
            self._store.save_run(run, created=True)
            run = self._continue(Engine.start(run, now()))
        return self._after(run)

    def _work(self, name: str) -> None:
        tasks = self._queues[name]
        while True:
            id = tasks.get()
            try:
                self._run_task(id)
            except Exception as e:  # the store or the engine failed: the run shows interrupted, to be resumed
                with self._lock:
                    self._active.discard(id)
                LOG.exception("run %s stopped: %s", id, e)
            finally:
                tasks.task_done()

    def _run_task(self, id: str) -> None:
        with self._lock:
            run = self._store.run(id)
            step = Engine.next(run) if run is not None and run.status == RunStatus.RUNNING else None
            if run is None or step is None or step.kind != StageKind.TASK:
                self._active.discard(id)
                return
            context = Engine.context(run, self.modules, self._store)
        try:
            output, error = step.action.run(context), None
        except PipelineError as e:
            output, error = None, str(e)
        except Exception as e:  # a bug in an action must not kill the worker: the run fails with it
            output, error = None, f"{type(e).__name__}: {e}"
        with self._lock:
            fresh = self._store.run(id)
            if (
                fresh is None
                or fresh.status != RunStatus.RUNNING
                or fresh.cursor != run.cursor
                or len(fresh.iterations) != len(run.iterations)
            ):
                self._active.discard(id)  # cancelled (or changed) while the task ran: what it did is dropped
                return
            if output is None:
                self._active.discard(id)
                self._store.save_run(Engine.fail(fresh, error or "the stage failed", now()))
                return
            fresh = self._continue(Engine.done(fresh, output, now()))
        self._after(fresh)

    # --- answers ---

    def decide(self, id: str, stage: str, decision: Decision) -> PipelineRun:
        with self._lock:
            run = self._load(id)
            item = self.inbox_item(run)
            decided = Engine.decide(run, decision, stage, now())  # validates before the score is sent
            if decision.score is not None and item is not None and item.experiment is not None:
                self.modules.chunking.score(item.experiment, decision.score)
            run = self._continue(decided)
        return self._after(run)

    def complete(self, id: str, stage: str, completion: Completion) -> PipelineRun:
        with self._lock:
            run = self._continue(Engine.complete(self._load(id), completion, stage, now()))
        return self._after(run)

    def cancel(self, id: str) -> PipelineRun:
        with self._lock:
            run = Engine.cancel(self._load(id), now())
            self._active.discard(id)
            self._store.save_run(run)
            return run

    def resume(self, id: str) -> PipelineRun:
        with self._lock:
            run = self._load(id)
            if run.id in self._active:
                raise ConflictError(f"the run {id} is running")
            run = self._continue(Engine.resume(run, now()))
        return self._after(run)

    def event(self, id: str, request: EventRequest) -> PipelineRun:
        with self._lock:
            run = Engine.event(self._load(id), request, now())
            self._store.save_run(run)
            return run
