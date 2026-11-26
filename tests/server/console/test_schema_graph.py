"""The schema drawn (feature 039): every label and every relationship, and a label reached again isn't drawn twice."""

from server.console.schema_graph import Edge, draw, roots

EDGES = [
    Edge("GENERA", "CHAT", "CONSULTA"),
    Edge("SOBRE", "CONSULTA", "JSON"),
    Edge("PERTENECE", "FACULTAD", "PROGRAMA"),
    Edge("HACE_PARTE", "PROGRAMA", "PIAA"),
    Edge("ES", "PIAA", "JSON"),
    Edge("TIENE", "JSON", "HALLAZGOS"),
]
LABELS = ["CHAT", "CONSULTA", "JSON", "FACULTAD", "PROGRAMA", "PIAA", "HALLAZGOS", "SUELTO"]


def test_it_starts_from_what_nothing_points_to_reaching_more_first() -> None:
    assert roots(LABELS, EDGES) == ["FACULTAD", "CHAT"]


def test_every_relationship_appears_once_and_a_repeated_label_is_only_named() -> None:
    lines = draw(LABELS, EDGES)
    assert sorted(line.relation for line in lines if line.relation) == sorted(edge.type for edge in EDGES)
    json_lines = [line for line in lines if line.label == "JSON"]
    assert [line.repeated for line in json_lines] == [False, True]
    assert {line.label for line in lines if line.label} == set(LABELS)


def test_a_cycle_with_no_root_is_drawn_too() -> None:
    lines = draw(["A", "B"], [Edge("X", "A", "B"), Edge("Y", "B", "A")])
    assert [(line.relation, line.label, line.repeated) for line in lines] == [
        ("", "A", False), ("X", "B", False), ("Y", "A", True)
    ]  # fmt: skip


def test_branches_show_what_hangs_from_what() -> None:
    lines = draw(["A", "B", "C"], [Edge("X", "A", "B"), Edge("Y", "A", "C")])
    assert [line.tree for line in lines] == ["", "├─ ", "└─ "]
