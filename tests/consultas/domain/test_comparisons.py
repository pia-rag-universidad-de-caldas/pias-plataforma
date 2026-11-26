"""comparison_batch (feature 060): a comparison and its panels' questions as one batch of data."""

import json

from consultas.domain import Asked, comparison_batch
from consultas.models import (
    Against,
    GraphLabel,
    GraphRelation,
    LlmOptions,
    PanelAnswer,
    PanelResult,
    PanelStatus,
    QuestionProperties,
    Response,
    Seconds,
    Source,
)

SOURCE = Source("f1", 0.8, "texto", ["Evaluación"], [2], "a" * 64, "2024/x.pdf", "020055", "Psicología")


def answered(index: int, against: Against | None = None, consulta: str = "q") -> Asked:
    laboratory = against is not None and against.laboratory
    stored: QuestionProperties = {
        "pregunta": "a",
        "respuesta": "r [1]",
        "modelo_llm": "qwen",
        "modelo_embedding": "m",
        "k": 5,
        "creado_en": "2026",
        "segundos": 1.5,
        "laboratorio": laboratory,
        "experimento_embedding": against.embeddings_experiment if against else None,
        "encontrada": True,
    }
    seconds = Seconds(0.5, 1.0)
    response = Response("r [1]", [SOURCE], "qwen", True, seconds, laboratory, [], [], stored)
    answer = PanelAnswer("r [1]", [SOURCE], consulta, "qwen", True, seconds, laboratory)
    result = PanelResult(index, f"P{index}", against, LlmOptions("qwen"), 5, PanelStatus.OK, answer=answer)
    return Asked(result, response)


def failed(index: int) -> Asked:
    return Asked(PanelResult(index, "mal", None, LlmOptions("x"), None, PanelStatus.ERROR, "llm is not answering"))


def test_each_answered_panel_hangs_its_question_from_the_comparison() -> None:
    batch = comparison_batch("c", "a", "2026", [answered(0, consulta="q0"), answered(1, consulta="q1")])
    compared = [(link.target.id, dict(link.properties)) for link in batch.links if link.type is GraphRelation.COMPARA]
    assert compared == [("q0", {"panel": 0, "etiqueta": "P0"}), ("q1", {"panel": 1, "etiqueta": "P1"})]
    assert not any(node.key.label is GraphLabel.CHAT for node in batch.nodes)


def test_a_failed_panel_stores_no_question_but_its_error() -> None:
    batch = comparison_batch("c", "a", "2026", [failed(0)])
    [node] = batch.nodes
    [panel] = json.loads(str(node.properties["paneles"]))
    assert node.key.label is GraphLabel.COMPARACION and batch.links == []
    assert (panel["estado"], panel["error"], panel["consulta"], panel["llm"]) == (
        "error",
        "llm is not answering",
        None,
        {"modelo": "x"},
    )


def test_a_citation_keeps_what_the_search_said_of_the_chunk() -> None:
    batch = comparison_batch("c", "a", "2026", [answered(0)])
    [cited] = [link for link in batch.links if link.type is GraphRelation.RESPONDIDA_CON]
    assert cited.target.label is GraphLabel.FRAGMENTOS
    assert dict(cited.properties) == {
        "puntaje": 0.8,
        "orden": 1,
        "sha256": "a" * 64,
        "origen": "2024/x.pdf",
        "codigo": "020055",
        "actividad": "Psicología",
    }


def test_a_laboratory_panel_cites_experiment_chunks_and_marks_the_comparison() -> None:
    batch = comparison_batch("c", "a", "2026", [answered(0), answered(1, Against("e1"), "q1")])
    comparison = next(n for n in batch.nodes if n.key.label is GraphLabel.COMPARACION)
    cited = {link.target.label for link in batch.links if link.type is GraphRelation.RESPONDIDA_CON}
    assert comparison.properties["laboratorio"] is True and cited == {GraphLabel.FRAGMENTOS, GraphLabel.EXP_CHUNK}


def test_a_panel_question_keeps_its_seconds_of_each_step() -> None:
    batch = comparison_batch("c", "a", "2026", [answered(0)])
    question = next(n for n in batch.nodes if n.key.label is GraphLabel.CONSULTA)
    assert (question.properties["segundos_busqueda"], question.properties["segundos_respuesta"]) == (0.5, 1.0)
