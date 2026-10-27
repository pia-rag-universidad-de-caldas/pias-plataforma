"""The body of POST /experiments turned into an ExperimentRequest (features 025 and 028): every parameter resolved
and checked, 422 with the first problem. Apart from the routes, so they only receive, launch and answer."""

from fastapi import HTTPException, status

from chunking.api.experiment_schemas import (
    ConversionBody,
    FilesBody,
    JsonFilesBody,
    NewExperiment,
    PagesBody,
    PlanBody,
    StrategyBody,
)
from chunking.domain import InvalidParameters, Parameters, Planner
from chunking.models import (
    ConversionParameters,
    DocumentFilter,
    ExperimentRequest,
    FileSelection,
    Inclusion,
    JsonSelection,
    Match,
    PageRange,
    Plan,
    PositionRange,
    RequestedStrategy,
    Rule,
    StrategyParameters,
)


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def _strategy(body: StrategyBody, where: str) -> StrategyParameters:
    try:
        return Parameters.resolve(
            RequestedStrategy(
                strategy=body.strategy,
                tokenizer=body.tokenizer,
                max_tokens=body.max_tokens,
                merge_peers=body.merge_peers,
                overlap_tokens=body.overlap_tokens,
                embedding_model=body.embedding_model,
                similarity_threshold=body.similarity_threshold,
            )
        )
    except InvalidParameters as error:
        raise _unprocessable(f"{where}: {error}") from error


def _pages(body: PagesBody | None, per_page: int | None, where: str) -> PageRange | None:
    if body is None:
        if per_page is not None:
            raise _unprocessable(f"{where}: per_page goes with pages")
        return None
    if body.first > body.last:
        raise _unprocessable(f"{where}.pages: from ({body.first}) is after to ({body.last})")
    if per_page is None:
        raise _unprocessable(f"{where}: pages need a per_page")
    return PageRange(body.first, body.last)


def _official(body: JsonFilesBody) -> JsonSelection:
    pages = _pages(body.pages, body.per_page, "files.from_json")
    if sum([body.all, pages is not None, bool(body.sha256s)]) != 1:
        raise _unprocessable("files.from_json: give exactly one of all, pages with per_page or sha256s")
    return JsonSelection(body.all, pages, body.per_page, body.sha256s)


def _files(files: FilesBody) -> FileSelection:
    """The files asked for, checked: exactly one form; 422 with the problem."""
    filters = bool(files.types or files.year or files.month or files.week or files.code)
    pages = _pages(files.pages, files.per_page, "files")
    ingesta = filters or files.limit is not None or files.all or pages is not None
    forms = [bool(files.sha256s), bool(files.from_experiment), files.from_json is not None, ingesta]
    if sum(forms) != 1:
        raise _unprocessable(
            "files: give exactly one of sha256s, from_experiment, from_json or ingesta's filters with limit, all or "
            "pages"
        )
    if ingesta and sum([files.limit is not None, files.all, pages is not None]) != 1:
        raise _unprocessable("files: ingesta's filters need exactly one of limit, all or pages with per_page")
    return FileSelection(
        sha256s=files.sha256s,
        filter=DocumentFilter(files.types, files.year, files.month, files.week, files.code) if ingesta else None,
        limit=files.limit,
        from_experiment=files.from_experiment,
        all=files.all,
        pages=pages,
        per_page=files.per_page,
        from_json=_official(files.from_json) if files.from_json is not None else None,
    )


def _plan(body: PlanBody) -> Plan:
    rules: list[Rule] = []
    for i, rule in enumerate(body.rules):
        position = rule.match.position
        match = Match(rule.match.titles, PositionRange(position.start, position.end) if position else None)
        try:
            Planner.check(match)
        except InvalidParameters as error:
            raise _unprocessable(f"plan.rules[{i}].match: {error}") from error
        rules.append(Rule(match, _strategy(rule.chunking, f"plan.rules[{i}].chunking")))
    return Plan(rules, _strategy(body.default, "plan.default"))


def experiment_request(new: NewExperiment, docling_version: str) -> ExperimentRequest:
    """The request with every parameter resolved and checked; 422 with the first problem."""
    files = _files(new.files)
    if files.from_json is not None:
        if new.plan is None:
            raise _unprocessable("files.from_json: official JSON is already converted, so it needs a plan")
        if new.conversion is not None:
            raise _unprocessable("files.from_json: each JSON keeps the conversion it was promoted with")
    conversion = new.conversion or ConversionBody()
    include = conversion.include
    return ExperimentRequest(
        name=new.name,
        description=new.description,
        files=files,
        conversion=ConversionParameters(
            heading_level=conversion.heading_level,
            numbered_titles=conversion.numbered_titles,
            table_structure=conversion.table_structure,
            table_mode=conversion.table_mode,
            include=Inclusion(
                include.tables, include.lists, include.page_headers, include.page_footers, include.pictures
            ),
            docling_version=docling_version,
        ),
        plan=_plan(new.plan) if new.plan is not None else None,
    )
