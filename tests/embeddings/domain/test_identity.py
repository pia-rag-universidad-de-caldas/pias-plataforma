import pytest

from embeddings.domain.identity import Identity, from_chunks, from_file_name, identify, passage_heading

# The headers as Docling and chunking left them in the real corpus (feature 057).
OLD = (
    "UNIVERSIDAD DE CALDAS\nPLAN INSTITUCIONAL DE ACTIVIDAD ACADÉMICA\nDepartamento que oferta: DISEÑO VISUAL "
    "Actividad académica: PSICOLOGÍA DE LA PERCEPCIÓN Código actividad académica: 0100105 Número de créditos que "
    "otorga: 1 Versión del PIAA: 1"
)
NEXT_LINE = (
    "Facultad que ofrece la Actividad Académica:\nCiencias exactas y naturales\nDepartamento que ofrece la Actividad "
    "Académica:\nFísica\nNombre de la Actividad Académica:\nSistemas termosolares\nCódigo de la Actividad Académica:\n"
    "616G7F\nVersión del Programa Institucional de la Actividad Académica (PIAA):"
)
LABELS_FIRST = (
    "Facultad que ofrece la Actividad Académica:\nDepartamento que ofrece la Actividad Académica:\nArtes y "
    "Humanidades\nEstudios Educativos\nNombre de la Actividad Académica:\nCódigo de la Actividad Académica:\n"
    "Educación y Pedagogía contemporáneas\n585G5K\nVersión del Programa Institucional de la Actividad Académica (PIAA):"
)
FOUR_LABELS = (
    "Facultad que ofrece la Actividad Académica:\nDepartamento que ofrece la Actividad Académica:\nNombre de la "
    "Actividad Académica:\nCódigo de la Actividad Académica:\nArtes y Humanidades\nMúsica\nCanto V II\nG5J0184"
)
SUBJECT = (
    "Nombre de la asignatura: Advanced Linguistic Expression\nTipo:\nCÓDIGO:\nDepartamento de adscripción:\n704G5F"
)
TRIPLETS = "Nombre de la Actividad Académica:, ## IDENTIFICACIÓN = Diseño Estratégico"


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        ([OLD], Identity("PSICOLOGÍA DE LA PERCEPCIÓN", "0100105")),
        (["CÓDIGO: R-2680-P-DC-774 VERSIÓN: 3", NEXT_LINE], Identity("Sistemas termosolares", "616G7F")),
        ([LABELS_FIRST], Identity("Educación y Pedagogía contemporáneas", "585G5K")),
        ([FOUR_LABELS], Identity("Canto V II", "G5J0184")),
        ([SUBJECT], Identity("Advanced Linguistic Expression", "704G5F")),
        ([TRIPLETS], Identity("Diseño Estratégico", None)),
        (["La percepción visiva no es el registro en frío de la realidad."], Identity()),
    ],
)
def test_the_course_is_read_from_the_header(texts: list[str], expected: Identity) -> None:
    assert from_chunks(texts) == expected


def test_a_form_code_is_never_the_course_code() -> None:
    assert from_chunks(["CÓDIGO: R-2680-P-DC-\n774\nVERSIÓN: 3"]).code is None


@pytest.mark.parametrize(
    ("file_name", "expected"),
    [
        ("2026-09-01-16.33.08.000000_PIAA_Sistemas_Termosolares.pdf", "Sistemas Termosolares"),
        ("2025-05-05-16.32.01.000000_Modelado_III_0010304.pdf", "Modelado III"),
        ("0100105-1.pdf", None),
        (None, None),
    ],
)
def test_the_name_may_come_from_the_file(file_name: str | None, expected: str | None) -> None:
    assert from_file_name(file_name) == expected


def test_the_file_name_is_used_only_without_a_name_in_the_header() -> None:
    assert identify([OLD], "PIAA_Otro.pdf").name == "PSICOLOGÍA DE LA PERCEPCIÓN"
    assert identify(["CÓDIGO ACTIVIDAD\nACADÉMICA: 0010304"], "Modelado_III.pdf") == Identity("Modelado III", None)


def test_the_heading_says_the_course() -> None:
    assert passage_heading(Identity("Cálculo I", "G7E0001")) == "Actividad académica: Cálculo I · código G7E0001\n"
    assert passage_heading(Identity()) == ""
