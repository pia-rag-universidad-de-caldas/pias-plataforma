"""embeddings only talks to data (feature 042's rule of the modules): its code names no route of another module."""

import re
from pathlib import Path

import embeddings

OTHERS = re.compile(r"""["'/](ingesta|parsing|chunking|pipeline)/""")


def test_embeddings_names_no_route_of_another_module() -> None:
    root = Path(embeddings.__file__).parent
    found = [
        f"{path.relative_to(root)}:{number}"
        for path in root.rglob("*.py")
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if OTHERS.search(line)
    ]
    assert found == []
