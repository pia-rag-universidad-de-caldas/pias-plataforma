"""The state machine of a run, without I/O: each function takes a run and gives the next one.

    queued → running → (task done → next stage | wait → waiting → answer → running) … → done
                     ↘ failed (a task or an external stage failed) → resume → running
    any but done/cancelled → cancelled

Who drives it (api/executor.py) asks `next` what to do: a task (it runs the action and gives `done`/`fail` the
result), a wait (`wait`, and the actor's answer comes through `decide` or `complete`), or None (the run is done).
"""

from dataclasses import dataclass, replace

from pipeline.models import (
    FILE_BATCH,
    FINAL,
    JSON_BATCH,
    Action,
    ActionContext,
    ActionOutput,
    Completion,
    ConflictError,
    Cursor,
    Decision,
    DecisionKind,
    Event,
    EventRequest,
    InboxItem,
    InvalidRequest,
    Iteration,
    IterationStatus,
    JsonObject,
    JsonValue,
    Modules,
    PipelineRun,
    RunRequest,
    RunStatus,
    RunStore,
    Stage,
    StageKind,
    StageRecord,
    Template,
    Waiting,
    approved,
)

from . import order
from .actions import REVIEW_SCORE, action
from .merge import deep_merge

EXTERNAL = "external"
RESUMABLE = frozenset({RunStatus.FAILED, RunStatus.INTERRUPTED, RunStatus.QUEUED, RunStatus.RUNNING})


@dataclass(frozen=True)
class Step:
    """What the run has to do now: `stage` (a step of `cycle` inside one) with its catalog action."""

    stage: Stage
    cycle: Stage | None
    action: Action

    @property
    def kind(self) -> StageKind:
        return self.action.kind


def _ids(stages: tuple[Stage, ...]) -> set[str]:
    return {i for s in stages for i in (s.id, *_ids(s.stages))}


def _at(run: PipelineRun) -> tuple[Stage, Stage | None] | None:
    """(stage, its cycle) at the cursor; None past the last stage."""
    top = run.template.stages
    if run.cursor.stage >= len(top):
        return None
    stage = top[run.cursor.stage]
    if run.cursor.step is None:
        return stage, None
    return stage.stages[run.cursor.step], stage


def _iteration(run: PipelineRun) -> Iteration | None:
    """The running iteration of the cycle at the cursor."""
    at = _at(run)
    if at is None or at[1] is None:
        return None
    cycle = at[1]
    return next((i for i in reversed(run.iterations) if i.stage == cycle.id), None)


def _with(run: PipelineRun, iteration: Iteration) -> tuple[Iteration, ...]:
    return tuple(iteration if (i.stage, i.index) == (iteration.stage, iteration.index) else i for i in run.iterations)


def _enter(run: PipelineRun, now: str) -> PipelineRun:
    """The run at its cursor: inside a cycle that starts, with its first iteration; past the end, done."""
    top = run.template.stages
    if run.cursor.stage >= len(top):
        return replace(run, status=RunStatus.DONE, finished=now, started=None, waiting=None)
    stage = top[run.cursor.stage]
    if stage.is_cycle and run.cursor.step is None:
        config = deep_merge(stage.params, run.params.get(stage.id, {}))
        index = 1 + sum(1 for i in run.iterations if i.stage == stage.id)
        started = Iteration(stage.id, index, config, now)
        return replace(run, cursor=Cursor(run.cursor.stage, 0), iterations=(*run.iterations, started), started=now)
    return replace(run, started=now)


def _advance(run: PipelineRun, now: str) -> PipelineRun:
    """To the next step of the cycle, or to the next stage of the template."""
    cursor = run.cursor
    at = _at(run)
    if at is not None and at[1] is not None and cursor.step is not None and cursor.step + 1 < len(at[1].stages):
        return replace(run, cursor=Cursor(cursor.stage, cursor.step + 1), started=now)
    return _enter(replace(run, cursor=Cursor(cursor.stage + 1)), now)


def _record(
    run: PipelineRun, stage: Stage, now: str, status: str, result: JsonValue = None, error: str | None = None
) -> PipelineRun:
    iteration = _iteration(run)
    record = StageRecord(
        stage=stage.id,
        status=status,
        started=run.started or now,
        finished=now,
        iteration=iteration.index if iteration else None,
        result=result,
        error=error,
    )
    return replace(run, records=(*run.records, record))


def _waiting_for(run: PipelineRun, stage: str, actor: str | None, kind: str) -> tuple[Waiting, Stage, Stage | None]:
    """The wait an answer is for; ConflictError if the run isn't waiting there, for that actor, for that kind."""
    waiting = run.waiting
    at = _at(run)
    if run.status != RunStatus.WAITING or waiting is None or at is None:
        raise ConflictError(f"the run {run.id} isn't waiting for anyone (it is {run.status})")
    if stage not in (waiting.stage, waiting.step):
        raise ConflictError(f"the run {run.id} is waiting at {waiting.step!r} ({waiting.stage!r}), not at {stage!r}")
    if actor is not None and actor != waiting.actor:
        raise ConflictError(f"{waiting.step!r} is waiting for {waiting.actor!r}, not for {actor!r}")
    step, cycle = at
    if step.action != kind:
        raise ConflictError(f"{waiting.step!r} is a {step.action}: answer it with the route of {step.action}")
    return waiting, step, cycle


def _retry(
    run: PipelineRun, cycle: Stage, step: Stage, scored: Iteration, waiting: Waiting, changes: JsonObject, now: str
) -> PipelineRun:
    """Closes the iteration as retried and opens the next one, with its configuration plus `changes`, at the start
    of the cycle."""
    if waiting.exhausted:
        raise ConflictError(f"the cycle {cycle.id!r} reached max_iterations ({cycle.max_iterations})")
    run = _record(run, step, now, "done", {"decision": "retry", "iteration": scored.index})
    closed = replace(scored, status=IterationStatus.RETRIED, finished=now)
    following = Iteration(cycle.id, scored.index + 1, deep_merge(scored.config, changes), now)
    return replace(
        run,
        iterations=(*_with(run, closed), following),
        cursor=Cursor(run.cursor.stage, 0),
        started=now,
    )


def _approve(run: PipelineRun, cycle: Stage, step: Stage, index: int, now: str) -> PipelineRun:
    """Approves iteration `index` of the cycle (its artifacts, approved, go to the run), discards the running one and
    goes on to the next stage."""
    chosen = next((i for i in run.iterations if i.stage == cycle.id and i.index == index), None)
    if chosen is None:
        raise InvalidRequest(f"the cycle {cycle.id!r} has no iteration {index}")
    run = _record(run, step, now, "done", {"decision": "approve", "iteration": index})
    iterations = tuple(
        i
        if i.stage != cycle.id
        else replace(i, status=IterationStatus.APPROVED, finished=i.finished or now)
        if i.index == index
        else replace(i, status=IterationStatus.DISCARDED, finished=now)
        if i.status == IterationStatus.RUNNING
        else i
        for i in run.iterations
    )
    artifacts = {**run.artifacts, **{approved(k): v for k, v in chosen.artifacts.items()}}
    return _enter(replace(run, iterations=iterations, artifacts=artifacts, cursor=Cursor(run.cursor.stage + 1)), now)


class Engine:
    @staticmethod
    def new(id: str, request: RunRequest, template: Template, now: str) -> PipelineRun:
        """A queued run with a copy of `template`; InvalidTemplate/InvalidRequest if it can't run."""
        order.check(template.stages)
        unknown = sorted(set(request.params) - _ids(template.stages))
        if unknown:
            raise InvalidRequest(f"`params` for stages the template doesn't have: {unknown}")
        return PipelineRun(
            id=id,
            name=request.name or f"{template.id} {id}",
            template=template,
            status=RunStatus.QUEUED,
            created=now,
            files=request.files,
            params=request.params,
        )

    @staticmethod
    def start(run: PipelineRun, now: str) -> PipelineRun:
        if run.status != RunStatus.QUEUED:
            raise ConflictError(f"the run {run.id} already started ({run.status})")
        return _enter(replace(run, status=RunStatus.RUNNING), now)

    @staticmethod
    def next(run: PipelineRun) -> Step | None:
        """What the run has to do now; None when there is nothing left (it is done)."""
        at = _at(run)
        if at is None:
            return None
        stage, cycle = at
        return Step(stage, cycle, action(stage))

    @staticmethod
    def context(run: PipelineRun, modules: Modules, store: RunStore) -> ActionContext:
        """What the task at the cursor gets: its configuration (its params, the run's for it, the iteration's) and
        the artifacts it can read (the run's and the running iteration's)."""
        at = _at(run)
        if at is None:
            raise ConflictError(f"the run {run.id} has nothing left to do")
        stage, _ = at
        iteration = _iteration(run)
        config = deep_merge(stage.params, run.params.get(stage.id, {}))
        if iteration is not None:
            config = deep_merge(config, iteration.config)
        artifacts = {**run.artifacts, **(iteration.artifacts if iteration else {})}
        return ActionContext(run, stage, config, artifacts, modules, store, iteration.index if iteration else None)

    @staticmethod
    def done(run: PipelineRun, output: ActionOutput, now: str) -> PipelineRun:
        """The task at the cursor ended well: its artifacts are kept (in the iteration, inside a cycle) and the run
        goes on."""
        at = _at(run)
        if at is None:
            raise ConflictError(f"the run {run.id} has nothing left to do")
        run = _record(run, at[0], now, "done", output.result)
        iteration = _iteration(run)
        if iteration is None:
            run = replace(run, artifacts={**run.artifacts, **output.artifacts})
        else:
            experiments = (*iteration.experiments, output.experiment) if output.experiment else iteration.experiments
            changed = replace(iteration, artifacts={**iteration.artifacts, **output.artifacts}, experiments=experiments)
            run = replace(run, iterations=_with(run, changed))
        return _advance(run, now)

    @staticmethod
    def fail(run: PipelineRun, error: str, now: str) -> PipelineRun:
        """The task at the cursor failed: the run stops there (resume repeats it)."""
        at = _at(run)
        if at is not None:
            run = _record(run, at[0], now, "failed", error=error)
        return replace(run, status=RunStatus.FAILED, error=error, waiting=None)

    @staticmethod
    def wait(run: PipelineRun, now: str) -> PipelineRun:
        """The run waits for the actor of the stage at the cursor (the cycle's, for a review)."""
        at = _at(run)
        if at is None:
            raise ConflictError(f"the run {run.id} has nothing left to do")
        stage, cycle = at
        actor = (cycle.actor if cycle and stage.action == REVIEW_SCORE else stage.actor) or ""
        iteration = _iteration(run)
        exhausted = bool(
            cycle
            and stage.action == REVIEW_SCORE
            and cycle.max_iterations
            and iteration
            and iteration.index >= cycle.max_iterations
        )
        waiting = Waiting(
            stage=cycle.id if cycle else stage.id,
            step=stage.id,
            actor=actor,
            since=now,
            iteration=iteration.index if iteration else None,
            exhausted=exhausted,
        )
        return replace(run, status=RunStatus.WAITING, waiting=waiting, started=run.started or now)

    @staticmethod
    def decide(run: PipelineRun, decision: Decision, stage: str, now: str) -> PipelineRun:
        """The answer of a cycle's actor at its review: retry (another iteration with the last configuration plus
        `next`) or approve (the chosen iteration's artifacts, approved, and on to the next stage)."""
        waiting, step, cycle = _waiting_for(run, stage, decision.actor, REVIEW_SCORE)
        iteration = _iteration(run)
        assert cycle is not None and iteration is not None  # a review only goes inside a cycle (order.check)
        scored = replace(iteration, score=decision.score if decision.score is not None else iteration.score)
        run = replace(run, iterations=_with(run, scored), waiting=None, status=RunStatus.RUNNING)
        if decision.kind == DecisionKind.RETRY:
            return _retry(run, cycle, step, scored, waiting, decision.next, now)
        if decision.next:
            raise InvalidRequest("`next` only goes with retry")
        return _approve(run, cycle, step, decision.iteration or iteration.index, now)

    @staticmethod
    def complete(run: PipelineRun, completion: Completion, stage: str, now: str) -> PipelineRun:
        """The answer of an external stage: its result fills what it gives; an error fails the run."""
        _, step, _ = _waiting_for(run, stage, completion.actor, EXTERNAL)
        run = replace(run, waiting=None, status=RunStatus.RUNNING)
        if completion.error:
            return Engine.fail(run, completion.error, now)
        gives = action(step).gives_of(step)
        artifacts: JsonObject = dict.fromkeys(gives, completion.result if completion.result is not None else True)
        return Engine.done(run, ActionOutput(artifacts, completion.result), now)

    @staticmethod
    def cancel(run: PipelineRun, now: str) -> PipelineRun:
        if run.status in FINAL:
            raise ConflictError(f"the run {run.id} is already {run.status}")
        iterations = tuple(
            replace(i, status=IterationStatus.DISCARDED, finished=now) if i.status == IterationStatus.RUNNING else i
            for i in run.iterations
        )
        return replace(run, status=RunStatus.CANCELLED, finished=now, waiting=None, iterations=iterations)

    @staticmethod
    def resume(run: PipelineRun, now: str) -> PipelineRun:
        """A failed or interrupted run, running again from the stage it stopped at (it is repeated)."""
        if run.status not in RESUMABLE:
            raise ConflictError(f"only a failed or interrupted run resumes; {run.id} is {run.status}")
        if run.status == RunStatus.QUEUED:
            return Engine.start(run, now)
        return replace(run, status=RunStatus.RUNNING, error=None, started=now)

    @staticmethod
    def event(run: PipelineRun, request: EventRequest, now: str) -> PipelineRun:
        """An actor's note (a call to embeber or modelscenter inside a cycle...): recorded, the state doesn't change."""
        event = Event(len(run.events) + 1, request.actor, request.kind, request.detail, now)
        return replace(run, events=(*run.events, event))

    @staticmethod
    def inbox_item(run: PipelineRun, answer: str) -> InboxItem | None:
        """What the waiting run asks of its actor; None if it isn't waiting. `answer` is the route to answer to."""
        waiting = run.waiting
        if run.status != RunStatus.WAITING or waiting is None:
            return None
        iteration = _iteration(run)
        artifacts = {**run.artifacts, **(iteration.artifacts if iteration else {})}
        batch = artifacts.get(JSON_BATCH) or artifacts.get(FILE_BATCH)
        return InboxItem(
            run=run.id,
            name=run.name,
            stage=waiting.stage,
            step=waiting.step,
            actor=waiting.actor,
            since=waiting.since,
            iteration=waiting.iteration,
            exhausted=waiting.exhausted,
            experiment=iteration.experiments[-1] if iteration and iteration.experiments else None,
            batch=[str(s) for s in batch] if isinstance(batch, list) else [],
            artifacts=artifacts,
            answer=answer,
        )

    @staticmethod
    def stage_id(run: PipelineRun) -> str | None:
        """The id of the stage at the cursor (a cycle's step inside one); None past the end."""
        at = _at(run)
        return at[0].id if at else None
