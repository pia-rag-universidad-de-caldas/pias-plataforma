"""The modules consultas calls, in memory behind an httpx.MockTransport: embeddings (/vectors, /experiments/{id}),
llm (/chat, /models, /config), data (search, batch, nodes, relationships) and parsing (/preview, for the attached
documents)."""

import json
from dataclasses import dataclass, field

import httpx

from common.http import Json
from consultas.adapters import HttpModules

type Row = dict[str, object]
type NodeId = tuple[str, str]
type LinkId = tuple[str, str, str, str, str]  # type, source label, source id, target label, target id

INDEX, EXPERIMENT_INDEX = "vec_fragmentos_m_2", "vec_exp_chunk_m_2"
DESCRIPTION = "Una tabla con los porcentajes de la evaluación."  # what the fake vision model sees in any image
PREVIEW: Row = {
    "name": "plan.pdf",
    "pages": 2,
    "truncated": False,
    "text": "Evaluación\nDos parciales.\n\nProyecto\nUna entrega.",
    "sections": [
        {"headings": ["Evaluación"], "text": "Dos parciales.", "pages": [1]},
        {"headings": ["Proyecto"], "text": "Una entrega.", "pages": [2]},
    ],
}


def admitted(name: str, vision: bool = False, installed: bool = True) -> Row:
    return {"name": name, "context": 32768, "vision": vision, "installed": installed, "default": False}


def hit(id: str, score: float) -> Row:
    return {
        "id": id,
        "score": score,
        "text": f"texto {id}",
        "headings": ["Evaluación"],
        "pages": [2],
        "sha256": "a" * 64,
        "origin": "2024/x.pdf",
        "code": "020055",
    }


@dataclass
class FakeModules:
    hits: list[Row] = field(default_factory=list)  # what data's search answers
    experiments: dict[str, Row] = field(default_factory=dict)  # GET /embeddings/experiments/{id}
    reply: str = "Se evalúa con dos parciales [1]."
    nodes: dict[NodeId, Row] = field(default_factory=dict)
    links: dict[LinkId, Row] = field(default_factory=dict)
    down: set[str] = field(default_factory=set)  # "embeddings", "llm", "data"
    llm_refuses: bool = False
    requests: list[tuple[str, str, object]] = field(default_factory=list)  # method, path, body
    searches: list[list[Row]] = field(default_factory=list)  # what each search answers, in order (then `hits`)
    preview: Row = field(default_factory=lambda: dict(PREVIEW))  # POST /parsing/preview
    preview_status: int = 200
    models: list[Row] = field(default_factory=lambda: [admitted("qwen"), admitted("qwen2.5vl:3b", vision=True)])
    active_model: str = "qwen"  # GET /llm/config

    # data

    def _batch(self, body: Json) -> httpx.Response:
        start = body.get("replace_from")
        if isinstance(start, dict):
            for link in [k for k in self.links if k[0] == "GENERA" and k[1:3] == (start["label"], start["id"])]:
                self.nodes.pop((link[3], link[4]), None)
                self.links = {k: v for k, v in self.links.items() if (link[3], link[4]) not in (k[1:3], k[3:5])}
        for n in body["nodes"]:
            node: NodeId = (str(n["label"]), str(n["id"]))
            properties: Row = dict(n["properties"])
            if n["mode"] == "merge" and node in self.nodes:
                properties = {**self.nodes[node], **properties}
            self.nodes[node] = properties
        for r in body["relationships"]:
            source, target = r["source"], r["target"]
            ends = (str(source["label"]), str(source["id"])), (str(target["label"]), str(target["id"]))
            if any(end not in self.nodes for end in ends):
                return httpx.Response(422, json={"detail": "a missing end"})
            self.links[(str(r["type"]), *ends[0], *ends[1])] = dict(r["properties"])
        return httpx.Response(200, json={"created": len(body["nodes"])})

    def _relationships(self, label: str, id: str) -> httpx.Response:
        if (label, id) not in self.nodes:
            return httpx.Response(404, json={"detail": "no node"})
        found = [
            {"type": t, "source": {"label": sl, "id": si}, "target": {"label": tl, "id": ti}, "properties": p}
            for (t, sl, si, tl, ti), p in sorted(self.links.items())
            if (sl, si) == (label, id) or (tl, ti) == (label, id)
        ]
        return httpx.Response(200, json=found)

    def _data(self, request: httpx.Request, parts: list[str]) -> httpx.Response:
        body: Json = json.loads(request.content) if request.content else {}
        if request.method == "POST" and parts == ["vectors", "search"]:
            if body["index"] not in (INDEX, EXPERIMENT_INDEX):
                return httpx.Response(404, json={"detail": "no index"})
            label = "EXP_CHUNK" if body.get("experiment") else "FRAGMENTOS"
            found = self.searches.pop(0) if self.searches else self.hits
            for row in found:  # the chunks found are in the graph, as in data
                self.nodes.setdefault((label, str(row["id"])), {"texto": row["text"]})
            return httpx.Response(200, json=found[: body["k"]])
        if request.method == "POST" and parts == ["batch"]:
            return self._batch(body)
        if parts[:1] == ["nodes"] and len(parts) == 2:
            nodes = [
                {"label": parts[1], "id": i, "properties": p} for (lb, i), p in self.nodes.items() if lb == parts[1]
            ]
            return httpx.Response(200, json={"page": 1, "pages": 1, "total": len(nodes), "nodes": nodes})
        if parts[:1] == ["nodes"] and len(parts) == 4:
            return self._relationships(parts[1], parts[2])
        if parts[:1] == ["nodes"] and len(parts) == 3:
            key = (parts[1], parts[2])
            if request.method == "DELETE":
                if self.nodes.pop(key, None) is None:
                    return httpx.Response(404, json={"detail": "no node"})
                self.links = {k: v for k, v in self.links.items() if key not in (k[1:3], k[3:5])}
                return httpx.Response(204)
            if key not in self.nodes:
                return httpx.Response(404, json={"detail": "no node"})
            return httpx.Response(200, json={"label": key[0], "id": key[1], "properties": self.nodes[key]})
        return httpx.Response(404, json={"detail": "Not Found"})

    # embeddings and llm

    def _embeddings(self, request: httpx.Request, parts: list[str]) -> httpx.Response:
        if request.method == "POST" and parts == ["vectors"]:
            body = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "model": body.get("model", "m"),
                    "max_tokens": body.get("max_tokens", 128),
                    "dimensions": 2,
                    "index": INDEX,
                    "experiment_index": EXPERIMENT_INDEX,
                    "vectors": [[1.0, 0.0] for _ in body["texts"]],
                },
            )
        if parts[:1] == ["experiments"] and len(parts) == 2 and parts[1] in self.experiments:
            return httpx.Response(200, json=self.experiments[parts[1]])
        return httpx.Response(404, json={"detail": "Not Found"})

    def _llm(self, request: httpx.Request, parts: list[str]) -> httpx.Response:
        if request.method == "POST" and parts == ["chat"]:
            if self.llm_refuses:
                return httpx.Response(422, json={"detail": "the model 'x' isn't admitted"})
            body = json.loads(request.content)
            describing = len(body["messages"]) == 1 and body["messages"][0].get("images")
            message = {"role": "assistant", "content": DESCRIPTION if describing else self.reply}
            model = body.get("model", "qwen")
            return httpx.Response(
                200, json={"model": model, "message": message, "prompt_tokens": 9, "answer_tokens": 3, "seconds": 0.5}
            )
        if request.method == "GET" and parts == ["models"]:
            return httpx.Response(200, json={"admitted": self.models, "installed": []})
        if request.method == "GET" and parts == ["config"]:
            return httpx.Response(200, json={"model": self.active_model, "temperature": 0.2})
        return httpx.Response(404, json={"detail": "Not Found"})

    def _parsing(self, request: httpx.Request, parts: list[str]) -> httpx.Response:
        if request.method == "POST" and parts == ["preview"]:
            if self.preview_status != 200:
                return httpx.Response(self.preview_status, json={"detail": "Docling can't read it"})
            return httpx.Response(200, json=self.preview)
        return httpx.Response(404, json={"detail": "Not Found"})

    def handle(self, request: httpx.Request) -> httpx.Response:
        service, *parts = request.url.path.strip("/").split("/")
        self.requests.append(
            (request.method, request.url.path, json.loads(request.content) if request.content else None)
        )
        if service in self.down:
            return httpx.Response(503, json={"detail": f"{service} is down"})
        handlers = {"data": self._data, "embeddings": self._embeddings, "llm": self._llm, "parsing": self._parsing}
        if service not in handlers:
            return httpx.Response(404, json={"detail": "Not Found"})
        return handlers[service](request, parts)

    def modules(self) -> HttpModules:
        return HttpModules("http://server", transport=httpx.MockTransport(self.handle))
