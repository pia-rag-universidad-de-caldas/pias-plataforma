"""llm only talks to data and Ollama (feature 042's rule of the modules): its code names no route of another module,
and the label it writes is data's."""

import re
from pathlib import Path

import llm
from data.models import Label
from llm.models import GraphLabel

OTHERS = re.compile(r"""["'/](ingesta|parsing|chunking|embeddings|pipeline|consultas)/""")


def test_llm_names_no_route_of_another_module() -> None:
    root = Path(llm.__file__).parent
    found = [
        f"{path.relative_to(root)}:{number}"
        for path in root.rglob("*.py")
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if OTHERS.search(line)
    ]
    assert found == []


def test_every_label_is_in_data() -> None:
    assert {label.value for label in GraphLabel} <= {label.value for label in Label}
