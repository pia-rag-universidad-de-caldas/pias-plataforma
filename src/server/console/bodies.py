"""JSON values and the body an operation's form starts from: a curated example for the bodies that are hard to guess
(runs, experiments, scores, pipeline decisions), otherwise empty: the form fills it from the body's schema."""

import copy
import json

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]

# (module, method, path inside the module) → body. Simulations first: sending the template as it is never writes.
TEMPLATES: dict[tuple[str, str, str], JsonValue] = {
    ("ingesta", "POST", "/runs"): {"source": {"kind": "folder"}, "simulate": True},
    ("data", "POST", "/batch"): {"nodes": [], "relationships": []},
    ("data", "POST", "/relationships"): {
        "type": "ES",
        "source": {"label": "PIAA", "id": ""},
        "target": {"label": "JSON", "id": ""},
        "properties": {},
    },
    ("chunking", "POST", "/runs"): {
        "simulate": True,
        "limit": 3,
        "types": ["pdf"],
        "retry_errors": False,
        "parameters": {"max_tokens": 512},
    },
    ("chunking", "POST", "/experiments"): {
        "name": "prueba",
        "description": "",
        "files": {"limit": 5, "types": ["pdf"]},
        "conversion": {"heading_level": 1},
        "plan": {
            "rules": [{"match": {"titles": ["objetivo"]}, "chunking": {"strategy": "points"}}],
            "default": {"strategy": "hybrid", "max_tokens": 512},
        },
        "simulate": True,
    },
    ("chunking", "POST", "/experiments/{id}/scores"): {
        "author": "analista",
        "criteria": {"coherencia": 4, "completitud": 3, "tamano": 5},
        "comment": "",
    },
    ("chunking", "PUT", "/experiments/{id}/scores/{score_id}"): {"author": "analista", "criteria": {"coherencia": 3}},
    ("chunking", "PATCH", "/experiments/{id}/scores/{score_id}"): {"criteria": {"tamano": 4}, "comment": ""},
    ("pipeline", "POST", "/runs"): {
        "template": "piaa",
        "name": "prueba",
        "files": {"pages": {"from": 1, "to": 1}, "per_page": 20, "types": ["pdf"]},
        "simulate": True,
    },
    ("pipeline", "POST", "/runs/{id}/stages/{stage}/decision"): {"decision": "approve", "actor": "lab"},
    ("pipeline", "POST", "/runs/{id}/stages/{stage}/complete"): {"actor": "embeber", "result": "ok"},
    ("pipeline", "POST", "/runs/{id}/events"): {"actor": "lab2", "kind": "note", "detail": {}},
    ("pipeline", "PUT", "/actors/{name}"): {"callback_url": "http://127.0.0.1:9000/hook"},
}


def dump(value: JsonValue) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def template(module: str, method: str, path: str) -> JsonObject:
    """The body an operation's form starts from: its curated example, or empty (the form fills it)."""
    found = TEMPLATES.get((module, method, path))
    return copy.deepcopy(found) if isinstance(found, dict) else {}
