"""scoped (feature 044): a production run's scope goes to the stages that read it."""

import pytest

from pipeline.domain import LABORATORY, PRODUCTION, scoped
from pipeline.models import InvalidRequest, Template


def test_the_scope_goes_to_the_chunking_stage_over_its_other_params() -> None:
    params = scoped(PRODUCTION.stages, {"chunkear": {"x": 1}}, "all")
    assert params == {"chunkear": {"x": 1, "scope": "all"}}


def test_no_scope_changes_nothing() -> None:
    assert scoped(PRODUCTION.stages, {"embeber": {}}, None) == {"embeber": {}}


@pytest.mark.parametrize(
    ("template", "scope", "message"), [(PRODUCTION, "some", "one of"), (LABORATORY, "all", "only goes")]
)
def test_an_unknown_scope_or_a_template_without_it(template: Template, scope: str, message: str) -> None:
    with pytest.raises(InvalidRequest, match=message):
        scoped(template.stages, {}, scope)
