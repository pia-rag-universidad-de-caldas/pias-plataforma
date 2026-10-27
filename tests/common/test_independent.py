"""common imports no module (feature 033): every module may import it, so it can't depend on any of them. Ruff can't
check it (TID251 is ignored in src/common/ for httpx and FastAPI), so this test does."""

import ast
from pathlib import Path

import common

MODULES = {"ingesta", "data", "chunking", "pipeline", "server"}


def test_common_imports_no_module() -> None:
    root = Path(common.__file__).parent
    found = []
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else []
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            found += [f"{path.relative_to(root)}: {n}" for n in names if n.split(".")[0] in MODULES]
    assert found == []
