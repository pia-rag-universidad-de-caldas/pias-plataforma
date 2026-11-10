"""The fingerprint of a parsing: Docling's version, PARSING_VERSION and every value of the fixed configuration. Same
file and same fingerprint = same parsing: it isn't done again."""

import hashlib
import json

from parsing.config import ParsingConfig


def fingerprint(config: ParsingConfig, version: int, docling: str) -> str:
    text = json.dumps({"config": config.as_dict(), "version": version, "docling": docling}, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]
