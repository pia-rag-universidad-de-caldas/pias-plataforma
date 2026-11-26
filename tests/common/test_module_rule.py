"""The rule of the modules (feature 042): the work modules never talk to each other. Each one only reads and writes in
data; only the pipeline orchestrates. Ruff can't see a route written as text, so this test does: nothing in a work
module names the prefix of another one but data's (neither the text nor its constant of common.config)."""

import re
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "src"
PREFIXES = {
    "ingesta": ("/ingesta", "INGESTA_PATH"),
    "parsing": ("/parsing", "PARSING_PATH"),
    "chunking": ("/chunking", "CHUNKING_PATH"),
    "pipeline": ("/pipeline", "PIPELINE_PATH"),
    "embeddings": ("/embeddings", "EMBEDDINGS_PATH"),
    "consultas": ("/consultas", "CONSULTAS_PATH"),
    "llm": ("/llm", "LLM_PATH"),
}


def references(module: str) -> list[str]:
    """Where `module` names the route of another module (data is everyone's storage: always allowed)."""
    root = SOURCE / module
    found: list[str] = []
    for path in sorted(root.rglob("*.py")) if root.is_dir() else []:
        text = path.read_text()
        for other, (prefix, constant) in PREFIXES.items():
            if other == module:
                continue
            route = re.compile(rf"[\"'`]{re.escape(prefix)}(/|[\"'`])")
            if route.search(text) or re.search(rf"\b{constant}\b", text):
                found.append(f"{path.relative_to(SOURCE)} → {other}")
    return found


@pytest.mark.parametrize("module", ["ingesta", "parsing", "chunking", "embeddings", "llm"])
def test_a_work_module_only_names_data(module: str) -> None:
    assert references(module) == []


def test_consultas_names_only_the_modules_of_its_answers() -> None:
    """consultas (the RAG, apart from the processing chain) calls embeddings (the question's vector), llm (the answer)
    and parsing (an attached document); what it needs of chunking's work it reads in data (feature 060)."""
    allowed = {"embeddings", "llm", "parsing"}
    assert [found for found in references("consultas") if found.rsplit(" → ", 1)[1] not in allowed] == []
