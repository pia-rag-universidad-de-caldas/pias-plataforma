"""The prompt: the marks replaced in one pass and the numbered context; the configuration's rules; the chat title."""

import pytest

from consultas.config import PROMPT, TITLE_LENGTH
from consultas.domain import config_problems, context, fill, title, usable
from consultas.models import ConsultasConfig, Source


def test_the_marks_are_replaced_once_and_other_braces_stay() -> None:
    assert fill("{x} {context} | {question}", "a {question}", "b") == "{x} a {question} | b"


def test_the_context_numbers_each_chunk_with_where_it_comes_from() -> None:
    found = context([Source("f", 0.9, " uno ", ["A", "B"], [2, 3], "s", "o.pdf", "020055")])
    assert found == "[1] o.pdf · PIAA 020055 · páginas 2, 3 · A > B\nuno"


def test_the_default_prompt_is_usable() -> None:
    assert config_problems(ConsultasConfig(5, 0.3, PROMPT, 3)) == []


@pytest.mark.parametrize(
    "config",
    [ConsultasConfig(0, 0.3, PROMPT, 3), ConsultasConfig(5, 2.0, PROMPT, 3), ConsultasConfig(5, 0.3, "{question}", 3)],
    ids=["k", "min_score", "prompt without context"],
)
def test_a_wrong_stored_configuration_gives_the_default(config: ConsultasConfig) -> None:
    assert config_problems(config) and usable(config).prompt == PROMPT


def test_a_long_question_is_cut_for_the_title() -> None:
    assert len(title("palabra " * 50)) == TITLE_LENGTH and title("  ¿Qué\n es?  ") == "¿Qué es?"
