"""JSON values and the body an operation's form starts from: a curated example for the bodies that are hard to guess
(runs, experiments, pipeline decisions), otherwise empty: the form fills it from the body's schema."""

import copy
import json

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]


def text_of(value: JsonValue) -> str:
    """A value of an answer as it is shown; nothing if there is none."""
    return "" if value is None else str(value)


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
    ("chunking", "POST", "/experiments"): {
        "name": "prueba",
        "description": "",
        "sha256s": [],
        "chunking": {"chunker": "hybrid", "max_tokens": 126},
        "simulate": True,
    },
    ("chunking", "PUT", "/config"): {"chunker": "hybrid", "max_tokens": 126, "merge_peers": True},
    ("chunking", "PATCH", "/config"): {"max_tokens": 126},
    ("chunking", "POST", "/runs"): {"sha256s": [], "simulate": True},
    ("parsing", "POST", "/runs"): {"sha256s": [], "redo": False, "simulate": True},
    ("parsing", "POST", "/preview"): {"name": "", "content": ""},
    ("embeddings", "POST", "/runs"): {"sha256s": [], "force": False, "simulate": True},
    ("embeddings", "POST", "/experiments"): {
        "name": "prueba",
        "description": "",
        "chunking_experiment": "",
        "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "max_tokens": 128,
        "simulate": True,
    },
    ("embeddings", "PUT", "/config"): {
        "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "max_tokens": 128,
    },
    ("embeddings", "PATCH", "/config"): {"max_tokens": 128},
    ("llm", "POST", "/models/pull"): {"name": "qwen2.5:0.5b"},
    ("llm", "PUT", "/config"): {"model": "llama3.1:8b", "temperature": 0.2, "num_ctx": 8192, "max_tokens": 1024},
    ("llm", "PATCH", "/config"): {"temperature": 0.2},
    ("llm", "POST", "/chat"): {"messages": [{"role": "user", "content": "Hola, ¿quién eres?"}]},
    ("embeddings", "POST", "/vectors"): {"texts": [""]},
    ("consultas", "POST", "/search"): {"question": "", "k": 5},
    ("consultas", "POST", "/ask"): {"question": ""},
    ("consultas", "PUT", "/config"): {"k": 5, "min_score": 0.3, "history": 3},
    ("consultas", "PATCH", "/config"): {"min_score": 0.3},
    ("pipeline", "POST", "/runs"): {
        "template": "laboratorio",
        "name": "prueba",
        "files": {"pages": {"from": 1, "to": 1}, "per_page": 20, "types": ["pdf"]},
        "params": {"laboratorio": {"chunking": {"chunker": "hybrid"}, "embeddings": {}}},
        "simulate": True,
    },
    ("pipeline", "POST", "/runs/{id}/stages/{stage}/decision"): {
        "decision": "retry",
        "actor": "lab",
        "score": {"score": 3, "criteria": {"coherencia": 3}, "author": "lab", "comment": ""},
        "next": {"chunking": {"max_tokens": 100}},
    },
    ("pipeline", "POST", "/runs/{id}/stages/{stage}/complete"): {"actor": "lab", "result": "ok"},
    ("pipeline", "POST", "/runs/{id}/events"): {"actor": "lab", "kind": "note", "detail": {}},
    ("pipeline", "PUT", "/actors/{name}"): {"callback_url": "http://127.0.0.1:9000/hook"},
}


def dump(value: JsonValue) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def template(module: str, method: str, path: str) -> JsonObject:
    """The body an operation's form starts from: its curated example, or empty (the form fills it)."""
    found = TEMPLATES.get((module, method, path))
    return copy.deepcopy(found) if isinstance(found, dict) else {}
