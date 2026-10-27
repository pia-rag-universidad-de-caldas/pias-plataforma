"""The models as JSON and back: the stages of a template and the selection (as the API receives them and as they are
stored), and the parts of a run that are stored as JSON text. Reading checks every value: a malformed one is
InvalidRequest (InvalidTemplate for stages), with where it is."""

from collections.abc import Sequence

from .concepts import JsonObject, JsonValue, Stage
from .ports import InvalidRequest, InvalidTemplate, as_object
from .requests import PageRange, Selection
from .results import Cursor, Event, Iteration, IterationStatus, StageRecord, Waiting

_STAGE_KEYS = frozenset({"id", "action", "params", "actor", "stages", "max_iterations", "needs", "gives"})
_SELECTION_KEYS = frozenset(
    {"all", "pages", "per_page", "sha256s", "from_run", "types", "year", "month", "week", "code"}
)


def _text(value: JsonValue, where: str, error: type[Exception] = InvalidRequest) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error(f"{where} must be a non-empty text, not {value!r}")
    return value


def _optional_text(value: JsonValue, where: str, error: type[Exception] = InvalidRequest) -> str | None:
    return None if value is None else _text(value, where, error)


def _integer(value: JsonValue, where: str, error: type[Exception] = InvalidRequest) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise error(f"{where} must be an integer, not {value!r}")
    return value


def _optional_integer(value: JsonValue, where: str, error: type[Exception] = InvalidRequest) -> int | None:
    return None if value is None else _integer(value, where, error)


def _texts(value: JsonValue, where: str, error: type[Exception] = InvalidRequest) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (_text(value, where, error),)  # one type may come alone: "pdf"
    if not isinstance(value, list):
        raise error(f"{where} must be a list of texts, not {value!r}")
    return tuple(_text(v, f"{where}[{i}]", error) for i, v in enumerate(value))


def _unknown(value: JsonObject, allowed: frozenset[str], where: str, error: type[Exception]) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise error(f"{where}: unknown keys {unknown} (allowed: {sorted(allowed)})")


# --- stages ---


def stage_from_json(value: JsonValue, where: str = "stage") -> Stage:
    try:
        raw = as_object(value, where)
    except InvalidRequest as e:
        raise InvalidTemplate(str(e)) from e
    _unknown(raw, _STAGE_KEYS, where, InvalidTemplate)
    id = _text(raw.get("id"), f"{where}.id", InvalidTemplate)
    where = f"stage {id!r}"
    children = raw.get("stages")
    if children is not None and not isinstance(children, list):
        raise InvalidTemplate(f"{where}: `stages` must be a list")
    params = raw.get("params")
    if params is not None and not isinstance(params, dict):
        raise InvalidTemplate(f"{where}: `params` must be an object")
    return Stage(
        id=id,
        action=_text(raw.get("action"), f"{where}.action", InvalidTemplate),
        params=params or {},
        actor=_optional_text(raw.get("actor"), f"{where}.actor", InvalidTemplate),
        stages=tuple(stage_from_json(c, f"{where}.stages[{i}]") for i, c in enumerate(children or [])),
        max_iterations=_optional_integer(raw.get("max_iterations"), f"{where}.max_iterations", InvalidTemplate),
        needs=_texts(raw.get("needs"), f"{where}.needs", InvalidTemplate),
        gives=_texts(raw.get("gives"), f"{where}.gives", InvalidTemplate),
    )


def stages_from_json(value: JsonValue) -> tuple[Stage, ...]:
    if not isinstance(value, list):
        raise InvalidTemplate(f"`stages` must be a list, not {value!r}")
    return tuple(stage_from_json(v, f"stages[{i}]") for i, v in enumerate(value))


def stage_to_json(stage: Stage) -> JsonObject:
    body: JsonObject = {"id": stage.id, "action": stage.action}
    if stage.params:
        body["params"] = stage.params
    if stage.actor is not None:
        body["actor"] = stage.actor
    if stage.stages:
        body["stages"] = [stage_to_json(s) for s in stage.stages]
    if stage.max_iterations is not None:
        body["max_iterations"] = stage.max_iterations
    if stage.needs:
        body["needs"] = list(stage.needs)
    if stage.gives:
        body["gives"] = list(stage.gives)
    return body


def stages_to_json(stages: Sequence[Stage]) -> list[JsonValue]:
    return [stage_to_json(s) for s in stages]


# --- selection ---


def selection_from_json(value: JsonValue, where: str = "files") -> Selection:
    """Exactly one of `all`, `pages`, `sha256s` and `from_run`; filters only with `all` or `pages`."""
    raw = as_object(value, where)
    _unknown(raw, _SELECTION_KEYS, where, InvalidRequest)
    pages: PageRange | None = None
    if raw.get("pages") is not None:
        bounds = as_object(raw["pages"], f"{where}.pages")
        _unknown(bounds, frozenset({"from", "to"}), f"{where}.pages", InvalidRequest)
        pages = PageRange(
            _integer(bounds.get("from"), f"{where}.pages.from"), _integer(bounds.get("to"), f"{where}.pages.to")
        )
        if not 1 <= pages.start <= pages.end:
            raise InvalidRequest(f"{where}.pages: must be 1 <= from <= to, not {pages.start}..{pages.end}")
    all_ = raw.get("all", False)
    if not isinstance(all_, bool):
        raise InvalidRequest(f"{where}.all must be true or false")
    selection = Selection(
        all=all_,
        pages=pages,
        per_page=_optional_integer(raw.get("per_page"), f"{where}.per_page"),
        sha256s=_texts(raw.get("sha256s"), f"{where}.sha256s"),
        from_run=_optional_text(raw.get("from_run"), f"{where}.from_run"),
        types=_texts(raw.get("types"), f"{where}.types"),
        year=_optional_integer(raw.get("year"), f"{where}.year"),
        month=_optional_integer(raw.get("month"), f"{where}.month"),
        week=_optional_text(raw.get("week"), f"{where}.week"),
        code=_optional_text(raw.get("code"), f"{where}.code"),
    )
    ways = [selection.all, selection.pages is not None, bool(selection.sha256s), selection.from_run is not None]
    if sum(ways) != 1:
        raise InvalidRequest(f"{where}: exactly one of `all`, `pages`, `sha256s` and `from_run`")
    if (selection.sha256s or selection.from_run) and (selection.filtered or selection.per_page is not None):
        raise InvalidRequest(f"{where}: the filters and `per_page` only go with `all` or `pages`")
    if selection.per_page is not None and selection.per_page < 1:
        raise InvalidRequest(f"{where}.per_page must be at least 1")
    if selection.month is not None and not 1 <= selection.month <= 12:
        raise InvalidRequest(f"{where}.month must be between 1 and 12")
    return selection


def selection_to_json(selection: Selection) -> JsonObject:
    body: JsonObject = {}
    if selection.all:
        body["all"] = True
    if selection.pages is not None:
        body["pages"] = {"from": selection.pages.start, "to": selection.pages.end}
    if selection.per_page is not None:
        body["per_page"] = selection.per_page
    if selection.sha256s:
        body["sha256s"] = list(selection.sha256s)
    if selection.from_run is not None:
        body["from_run"] = selection.from_run
    if selection.types:
        body["types"] = list(selection.types)
    for key, value in (("year", selection.year), ("month", selection.month)):
        if value is not None:
            body[key] = value
    for key, text in (("week", selection.week), ("code", selection.code)):
        if text is not None:
            body[key] = text
    return body


# --- the parts of a run stored as JSON (written by the pipeline itself: read back without the API's messages) ---


def cursor_to_json(cursor: Cursor) -> JsonObject:
    return {"stage": cursor.stage, "step": cursor.step}


def cursor_from_json(value: JsonValue) -> Cursor:
    raw = as_object(value, "cursor")
    return Cursor(_integer(raw.get("stage"), "cursor.stage"), _optional_integer(raw.get("step"), "cursor.step"))


def iteration_to_json(iteration: Iteration) -> JsonObject:
    return {
        "stage": iteration.stage,
        "index": iteration.index,
        "config": iteration.config,
        "started": iteration.started,
        "status": iteration.status.value,
        "artifacts": iteration.artifacts,
        "experiments": list(iteration.experiments),
        "score": iteration.score,
        "finished": iteration.finished,
    }


def iteration_from_json(value: JsonValue) -> Iteration:
    raw = as_object(value, "iteration")
    score = raw.get("score")
    return Iteration(
        stage=_text(raw.get("stage"), "iteration.stage"),
        index=_integer(raw.get("index"), "iteration.index"),
        config=as_object(raw.get("config"), "iteration.config"),
        started=_text(raw.get("started"), "iteration.started"),
        status=IterationStatus(_text(raw.get("status"), "iteration.status")),
        artifacts=as_object(raw.get("artifacts"), "iteration.artifacts"),
        experiments=_texts(raw.get("experiments"), "iteration.experiments"),
        score=None if score is None else as_object(score, "iteration.score"),
        finished=_optional_text(raw.get("finished"), "iteration.finished"),
    )


def record_to_json(record: StageRecord) -> JsonObject:
    return {
        "stage": record.stage,
        "status": record.status,
        "started": record.started,
        "finished": record.finished,
        "iteration": record.iteration,
        "result": record.result,
        "error": record.error,
    }


def record_from_json(value: JsonValue) -> StageRecord:
    raw = as_object(value, "record")
    return StageRecord(
        stage=_text(raw.get("stage"), "record.stage"),
        status=_text(raw.get("status"), "record.status"),
        started=_text(raw.get("started"), "record.started"),
        finished=_text(raw.get("finished"), "record.finished"),
        iteration=_optional_integer(raw.get("iteration"), "record.iteration"),
        result=raw.get("result"),
        error=_optional_text(raw.get("error"), "record.error"),
    )


def event_to_json(event: Event) -> JsonObject:
    return {
        "index": event.index,
        "actor": event.actor,
        "kind": event.kind,
        "detail": event.detail,
        "created": event.created,
    }


def event_from_json(value: JsonValue) -> Event:
    raw = as_object(value, "event")
    return Event(
        index=_integer(raw.get("index"), "event.index"),
        actor=_text(raw.get("actor"), "event.actor"),
        kind=_text(raw.get("kind"), "event.kind"),
        detail=raw.get("detail"),
        created=_text(raw.get("created"), "event.created"),
    )


def waiting_to_json(waiting: Waiting) -> JsonObject:
    return {
        "stage": waiting.stage,
        "step": waiting.step,
        "actor": waiting.actor,
        "since": waiting.since,
        "iteration": waiting.iteration,
        "exhausted": waiting.exhausted,
    }


def waiting_from_json(value: JsonValue) -> Waiting:
    raw = as_object(value, "waiting")
    exhausted = raw.get("exhausted", False)
    return Waiting(
        stage=_text(raw.get("stage"), "waiting.stage"),
        step=_text(raw.get("step"), "waiting.step"),
        actor=_text(raw.get("actor"), "waiting.actor"),
        since=_text(raw.get("since"), "waiting.since"),
        iteration=_optional_integer(raw.get("iteration"), "waiting.iteration"),
        exhausted=exhausted is True,
    )
