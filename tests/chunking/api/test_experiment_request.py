"""The checks of POST /chunking/experiments on its `files` and `plan` (features 025 and 028), without a server."""

import pytest
from fastapi import HTTPException

from chunking.api.experiment_requests import experiment_request
from chunking.api.experiment_schemas import ConversionBody, FilesBody, JsonFilesBody, NewExperiment, PagesBody, PlanBody
from chunking.models import PageRange


def request(files: FilesBody, plan: PlanBody | None = None, conversion: ConversionBody | None = None) -> NewExperiment:
    return NewExperiment(name="e", files=files, plan=plan, conversion=conversion)


def test_pages_with_types_and_no_plan_is_a_conversion_only_request() -> None:
    files = FilesBody(pages=PagesBody(first=2, last=4), per_page=50, types=["pdf", "docx"])
    built = experiment_request(request(files), "2")
    assert built.plan is None
    assert built.files.pages == PageRange(2, 4) and built.files.per_page == 50
    assert built.files.filter is not None and built.files.filter.types == ["pdf", "docx"]


def test_from_json_with_a_plan() -> None:
    files = FilesBody(from_json=JsonFilesBody(pages=PagesBody(first=1, last=1), per_page=10))
    built = experiment_request(request(files, PlanBody()), "2")
    assert built.files.from_json is not None and built.plan is not None


@pytest.mark.parametrize(
    ("files", "plan", "conversion"),
    [
        (FilesBody(pages=PagesBody(first=3, last=2), per_page=5), None, None),  # from after to
        (FilesBody(pages=PagesBody(first=1, last=2)), None, None),  # pages without per_page
        (FilesBody(per_page=5, all=True), None, None),  # per_page without pages
        (FilesBody(all=True, limit=3), None, None),  # two ingesta forms
        (FilesBody(types=["pdf"]), None, None),  # filters alone
        (FilesBody(all=True, sha256s=["ab" * 32]), None, None),  # two forms
        (FilesBody(from_json=JsonFilesBody(all=True)), None, None),  # from_json without a plan
        (FilesBody(from_json=JsonFilesBody(all=True)), PlanBody(), ConversionBody()),  # from_json with a conversion
        (FilesBody(from_json=JsonFilesBody()), PlanBody(), None),  # from_json with no form
    ],
)
def test_malformed_files_are_422(files: FilesBody, plan: PlanBody | None, conversion: ConversionBody | None) -> None:
    with pytest.raises(HTTPException) as error:
        experiment_request(request(files, plan, conversion), "2")
    assert error.value.status_code == 422
