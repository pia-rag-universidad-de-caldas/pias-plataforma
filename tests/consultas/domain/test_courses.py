import pytest

from consultas.domain.courses import named, rerank, topic, words
from consultas.models import CourseMatch, Source


def course(name: str | None, code: str | None = None, sha256: str = "a") -> CourseMatch:
    return CourseMatch(sha256 * 64, name, code, 1.0)


def test_words_are_folded_stemmed_and_without_stop_words() -> None:
    assert words("¿Qué EVALÚA la Percepción de las imágenes?") == {"evalua", "percepcion", "imagen"}


def test_a_name_with_most_of_its_words_in_the_question_is_named() -> None:
    found = course("PSICOLOGÍA DE LA PERCEPCIÓN")
    assert named("¿qué evalúa psicologia de la percepcion?", [found, course("Percepción remota", sha256="b")]) == [
        found
    ]


def test_every_version_of_the_named_course_stays() -> None:
    versions = [course("Estadística Aplicada", sha256=s) for s in "abc"]
    assert named("bibliografía de estadística aplicada", versions) == versions


def test_the_name_with_more_words_in_the_question_wins() -> None:
    long, short = course("Historia del arte IV", sha256="a"), course("Historia del arte", sha256="b")
    assert named("¿qué se lee en historia del arte IV?", [short, long]) == [long]


def test_a_course_code_names_its_course() -> None:
    found = course("Seminario electivo", "G6K0346")
    assert named("¿cuántos créditos tiene g6k0346?", [found]) == [found]


@pytest.mark.parametrize(
    ("question", "expected"),
    [("¿cómo se calcula la varianza en estadística?", 0), ("¿qué evalúa el curso de estadística?", 1)],
)
def test_a_one_word_name_needs_a_cue(question: str, expected: int) -> None:
    assert len(named(question, [course("ESTADÍSTICA")])) == expected


def test_a_question_with_few_of_the_words_names_nothing() -> None:
    assert named("¿qué es la percepción?", [course("Psicología de la percepción visual")]) == []


def chunk(id: str, score: float, headings: list[str], text: str = "texto") -> Source:
    return Source(id, score, text, headings, [1], "a" * 64, None, None)


def test_the_topic_is_the_question_without_the_course() -> None:
    assert topic("¿Qué evalúa el curso Psicología de la percepción?", [course("PSICOLOGÍA DE LA PERCEPCIÓN")]) == {
        "evalua"
    }


def test_a_section_named_like_the_topic_goes_up() -> None:
    justification = chunk("j", 0.90, ["JUSTIFICACIÓN"])
    evaluation = chunk("e", 0.78, ["CRITERIOS DE EVALUACIÓN"])
    assert [s.id for s in rerank([justification, evaluation], {"evalua"}, 1)] == ["e"]


def test_another_name_of_the_section_counts() -> None:
    books = chunk("b", 0.70, ["LIBROS"], "ARNHEIM, R. El pensamiento visual")
    method = chunk("m", 0.75, ["METODOLOGÍA"], "a partir de las lecturas")  # only its text: a third
    assert [s.id for s in rerank([method, books], {"bibliografia"}, 1)] == ["b"]


def test_a_repeated_text_is_left_once_and_scores_stay_the_cosine() -> None:
    first, again = chunk("1", 0.8, [], "lo mismo"), chunk("2", 0.79, [], "lo  mismo")
    found = rerank([first, again, chunk("3", 0.5, [])], set(), 3)
    assert [s.id for s in found] == ["1", "3"] and found[0].score == 0.8
