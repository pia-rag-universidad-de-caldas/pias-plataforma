"""The stages an actor does: scoring a cycle's iteration, and any external work."""

from pipeline.models import Action, Stage, StageKind


class ReviewScore(Action):
    name = "review.score"
    kind = StageKind.WAIT
    description = (
        "the cycle's actor reads the result in data (chunks and vectors), scores the iteration and decides:"
        " approve, or retry with another configuration (POST /pipeline/runs/{id}/stages/{cycle}/decision);"
        " always the last stage of a cycle"
    )


class External(Action):
    name = "external"
    kind = StageKind.WAIT
    description = "an actor does it and answers POST /pipeline/runs/{id}/stages/{stage}/complete"
    parameters = "actor (required), needs and gives: the artifacts the actor declares; its result fills `gives`"

    def needs_of(self, stage: Stage) -> tuple[str, ...]:
        return stage.needs

    def gives_of(self, stage: Stage) -> tuple[str, ...]:
        return stage.gives
