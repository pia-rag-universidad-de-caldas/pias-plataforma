"""What the actions share: the ids an earlier stage left, a job that must have ended well, a run's name."""

from pipeline.models import ActionContext, ActionError, JobOutcome


def ids(context: ActionContext, artifact: str) -> list[str]:
    """The sha256s an earlier stage left in `artifact` (an empty list is valid: there is nothing to do)."""
    found = context.artifacts.get(artifact)
    if found is None:
        raise ActionError(f"{context.stage.id}: no stage before it left {artifact}")
    if not isinstance(found, list):
        raise ActionError(f"{context.stage.id}: {artifact} isn't a list of sha256s")
    return [str(s) for s in found]


def ended_well(what: str, outcome: JobOutcome) -> JobOutcome:
    """`outcome`, or ActionError if the job didn't succeed."""
    if not outcome.succeeded:
        raise ActionError(f"{what} {outcome.id} ended {outcome.status}: {outcome.error or 'no detail'}")
    return outcome


def run_name(context: ActionContext) -> str:
    iteration = f" #{context.iteration}" if context.iteration is not None else ""
    return f"{context.run.name} · {context.stage.id}{iteration}"
