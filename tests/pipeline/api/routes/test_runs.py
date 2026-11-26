"""GET /runs?status=interrupted keeps the executor's derived status while reading indexed rows."""

from fastapi.testclient import TestClient

from pipeline.api import ApiSettings, create_app
from pipeline.models import PipelineRun, RunStatus, Template


def test_interrupted_filter_reads_queued_and_running_rows_then_checks_executor_status() -> None:
    template = Template("t", "template", "", ())
    queued = PipelineRun("q", "queued run", template, RunStatus.QUEUED, "2026-01-01T00:00:00")
    running = PipelineRun("r", "running run", template, RunStatus.RUNNING, "2026-01-02T00:00:00")

    class Runs:
        def __init__(self) -> None:
            self.calls: list[RunStatus] = []

        def runs_by_status(self, status: RunStatus, actor: str | None = None) -> list[PipelineRun]:
            self.calls.append(status)
            return {RunStatus.QUEUED: [queued], RunStatus.RUNNING: [running]}[status]

    app = create_app(ApiSettings("http://server.test"))
    store = Runs()
    app.state.store = store
    app.state.executor._active.add("r")
    answer = TestClient(app).get("/runs?status=interrupted")

    assert answer.status_code == 200
    assert [run["id"] for run in answer.json()] == ["q"]
    assert [run["status"] for run in answer.json()] == ["interrupted"]
    assert store.calls == [RunStatus.QUEUED, RunStatus.RUNNING]
