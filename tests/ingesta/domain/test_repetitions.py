"""Repeated PIAA (Repetitions): the reason of each upload against the previous one and which codes count."""

from dataclasses import replace

from ingesta.domain import Repetitions
from ingesta.models import FileRecord, Reason

BASE = FileRecord(
    origen="2024/01/Semana_01/020055/a.pdf",
    destino="vigentes/pdf/a.pdf",
    anio=2024,
    mes="01",
    mes_num=1,
    semana="Semana_01",
    codigo="020055",
    nombre="a.pdf",
    tipo="pdf",
    bytes=5000,
    modificado="2024-01-01T00:00:00",
    procesado_en="2024-02-01T00:00:00",
    accion="copiado",
    sha256="h1",
    completo=True,
)


def test_the_first_reason_that_holds_wins() -> None:
    other = replace(BASE, origen="b.pdf")
    assert Repetitions.reason(BASE, other) is Reason.EXACT_COPY
    no_piaa = replace(other, sha256="h9", nombre="SIN_PIAA.pdf")
    assert Repetitions.reason(BASE, no_piaa) is Reason.NO_PIAA
    assert Repetitions.reason(BASE, replace(other, sha256="h9", tipo="docx")) is Reason.OTHER_FORMAT
    prefixed = replace(other, sha256="h9", nombre="2025-01-28-16.16.41.000000_A.PDF")
    assert Repetitions.reason(BASE, prefixed) is Reason.SAME_NAME
    assert Repetitions.reason(BASE, replace(other, sha256="h9", nombre="z.pdf")) is Reason.OTHER_NAME


def test_an_empty_previous_upload_is_never_an_exact_copy() -> None:
    empty = replace(BASE, bytes=0)
    assert Repetitions.reason(empty, replace(BASE, origen="b.pdf", bytes=0)) is not Reason.EXACT_COPY


def test_repeated_codes_skip_the_unassigned_one() -> None:
    a = replace(BASE, origen="a.pdf", codigo="000000")
    b = replace(BASE, origen="b.pdf", codigo="000000", modificado="2024-02-01T00:00:00")
    c = replace(BASE, origen="c.pdf", modificado="2024-02-01T00:00:00")
    [repeated] = Repetitions.group([a, b, BASE, c])
    assert (repeated.code, [u.record.origen for u in repeated.uploads]) == ("020055", [BASE.origen, "c.pdf"])
    assert repeated.uploads[1].seconds == 31 * 86400
