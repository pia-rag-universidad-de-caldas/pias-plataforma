"""How a DoclingDocument is stored on its JSON node: as JSON, gzip and base64 (a string, what Neo4j stores). Several
times smaller than the JSON; whoever reads it (chunking) undoes the three steps."""

import base64
import gzip
import json
from collections.abc import Mapping


def encode(document: Mapping[str, object]) -> tuple[str, int]:
    """The stored text and the size of the JSON before compressing it."""
    raw = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii"), len(raw)


def decode(text: str) -> Mapping[str, object] | None:
    """The DoclingDocument of a stored text; None if it isn't one."""
    try:
        loaded = json.loads(gzip.decompress(base64.b64decode(text, validate=True)))
    except (ValueError, OSError, EOFError):
        return None
    return loaded if isinstance(loaded, dict) else None
