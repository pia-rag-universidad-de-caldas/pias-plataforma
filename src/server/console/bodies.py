"""JSON values and the body an operation's form starts from: a curated example for the bodies that are hard to guess
(runs, experiments, pipeline decisions), otherwise empty: the form fills it from the body's schema."""

import copy
import json

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]


def text_of(value: JsonValue) -> str:
    """A value of an answer as it is shown; nothing if there is none."""
    return "" if value is None else str(value)


MINILM = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# The body POST /pipeline/runs starts from for each incorporated template: choosing another `template` in its form
# loads that one's (feature 062). Production goes by parts (feature 056); experimentos chooses parsed documents,
# chunks them in a new experiment (or extends one, or takes the official chunks) and embeds with one model or more.
RUN_BODIES: dict[str, JsonObject] = {
    "produccion": {
        "template": "produccion",
        "name": "prueba",
        "files": {"pages": {"from": 1, "to": 1}, "per_page": 100, "types": ["pdf"]},
        "part_size": 20,
        "simulate": True,
    },
    "laboratorio": {
        "template": "laboratorio",
        "name": "prueba",
        "files": {"pages": {"from": 1, "to": 1}, "per_page": 5, "types": ["pdf"]},
        "params": {"laboratorio": {"chunking": {"chunker": "hybrid", "max_tokens": 126}}},
        "simulate": True,
    },
    "experimentos": {
        "template": "experimentos",
        "name": "prueba",
        "files": {"sample": 20, "seed": 7, "types": ["pdf"]},
        "params": {
            "chunkear": {"experiment": {"name": "hybrid 126", "chunking": {"chunker": "hybrid", "max_tokens": 126}}},
            "embeber": {"models": [MINILM]},
        },
        "simulate": True,
    },
}

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
        "all": False,
        "chunking": {"chunker": "hybrid", "max_tokens": 126},
        "simulate": True,
    },
    ("chunking", "PUT", "/config"): {"chunker": "hybrid", "max_tokens": 126, "merge_peers": True},
    ("chunking", "PATCH", "/config"): {"max_tokens": 126},
    ("chunking", "POST", "/runs"): {"sha256s": [], "simulate": True},
    ("chunking", "POST", "/experiments/{id}/documents"): {"sha256s": [], "simulate": True},  # feature 062
    ("embeddings", "POST", "/experiments/{id}/resume"): {"sha256s": []},  # feature 062: without, all that is missing
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
    ("consultas", "POST", "/compare"): {"question": "", "panels": [{"label": "Panel 1"}, {"label": "Panel 2"}]},
    ("consultas", "PUT", "/config"): {"k": 5, "min_score": 0.3, "history": 3},
    ("consultas", "PATCH", "/config"): {"min_score": 0.3},
    ("pipeline", "POST", "/runs"): RUN_BODIES["produccion"],  # the others: choosing their template (feature 062)
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


RUN_KEY = ("pipeline", "POST", "/runs")


def switched_body(key: tuple[str, str, str], before: str, now: str, name: str) -> JsonObject | None:
    """The body to start from again when the form of POST /pipeline/runs changes its `template` from `before` to
    `now` (an incorporated one), keeping the run's `name`; None if nothing changes."""
    if key != RUN_KEY or now == before or now not in RUN_BODIES:
        return None
    body = copy.deepcopy(RUN_BODIES[now])
    if name.strip():
        body["name"] = name.strip()
    return body


def dump(value: JsonValue) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def template(module: str, method: str, path: str) -> JsonObject:
    """The body an operation's form starts from: its curated example, or empty (the form fills it)."""
    found = TEMPLATES.get((module, method, path))
    return copy.deepcopy(found) if isinstance(found, dict) else {}
