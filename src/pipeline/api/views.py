"""The models as answers of the routes."""

from pipeline.domain import Engine
from pipeline.domain.codec import (
    cursor_to_json,
    event_to_json,
    iteration_to_json,
    record_to_json,
    selection_to_json,
    stage_to_json,
    stages_to_json,
    waiting_to_json,
)
from pipeline.models import Action, PipelineRun, RunStatus, Template

from .schemas import ActionView, RunSummary, RunView, TemplateView


def action_view(action: Action) -> ActionView:
    return ActionView(
        action.name,
        action.kind.value,
        action.module,
        list(action.needs),
        list(action.gives),
        action.description,
        action.parameters,
    )


def template_view(template: Template) -> TemplateView:
    return TemplateView(
        template.id,
        template.name,
        template.description,
        template.builtin,
        template.created,
        template.modified,
        stages_to_json(template.stages),
    )


def run_summary(run: PipelineRun, status: RunStatus) -> RunSummary:
    return RunSummary(
        run.id,
        run.name,
        run.template.id,
        status.value,
        run.created,
        run.finished,
        Engine.stage_id(run),
        waiting_to_json(run.waiting) if run.waiting else None,
    )


def run_view(run: PipelineRun, status: RunStatus) -> RunView:
    return RunView(
        id=run.id,
        name=run.name,
        status=status.value,
        created=run.created,
        started=run.started,
        finished=run.finished,
        error=run.error,
        stage=Engine.stage_id(run),
        waiting=waiting_to_json(run.waiting) if run.waiting else None,
        template={
            "id": run.template.id,
            "name": run.template.name,
            "stages": [stage_to_json(s) for s in run.template.stages],
        },
        files=selection_to_json(run.files) if run.files else None,
        params=dict(run.params.items()),
        cursor=cursor_to_json(run.cursor),
        artifacts=run.artifacts,
        iterations=[iteration_to_json(i) for i in run.iterations],
        records=[record_to_json(r) for r in run.records],
        events=[event_to_json(e) for e in run.events],
    )
