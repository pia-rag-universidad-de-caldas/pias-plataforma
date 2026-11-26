"""Fakes shared by tests of different folders that a test also names as a type (a fixture alone can't: conftest
isn't importable). On the path through pytest's `pythonpath` and mypy's `mypy_path`."""

import json
from collections import Counter

import httpx

from common.http import Json
from embeddings.config import MODELS
from embeddings.models import (
    DocumentError,
    EmbeddableChunk,
    EmbeddableDocument,
    EmbeddingConfig,
    GraphBatch,
    UpstreamDown,
    VectorIndexSpec,
)


class FakeData:
    """data's GET /data/nodes/{label}[/{id}] (with ?omit) and POST /data/batch over a dict, with the modes of data
    (replace, merge: a null removes the property, ensure). `batches` keeps every body; `down` answers 503."""

    def __init__(self) -> None:
        self.nodes: dict[tuple[str, str], dict[str, object]] = {}
        self.links: set[tuple[str, str, str, str, str]] = set()
        self.batches: list[dict[str, object]] = []
        self.down = False
        self.refuse: set[str] = set()  # ids whose batch data refuses (422)
        self.indexes: dict[str, dict[str, object]] = {}  # PUT /data/vectors/indexes/{name} (feature 046)
        self.dropped: list[tuple[str, bool]] = []  # DELETE /data/vectors/indexes/{name}: (name, drop_property)

    def _page(self, label: str, request: httpx.Request) -> httpx.Response:
        omit = set(request.url.params.get_list("omit"))
        page, per_page = int(request.url.params.get("page", "1")), int(request.url.params.get("per_page", "50"))
        found = sorted((id, p) for (lab, id), p in self.nodes.items() if lab == label)
        chosen = found[(page - 1) * per_page : page * per_page]
        nodes = [
            {"label": label, "id": id, "properties": {k: v for k, v in p.items() if k not in omit}} for id, p in chosen
        ]
        return httpx.Response(200, json={"nodes": nodes, "total": len(found), "pages": -(-len(found) // per_page)})

    def _batch(self, body: Json) -> httpx.Response:
        nodes = body.get("nodes") or []
        if any(n.get("id") in self.refuse for n in nodes):
            return httpx.Response(422, json={"detail": "refused"})
        known = set(self.nodes) | {(str(n["label"]), str(n["id"])) for n in nodes}
        ends = [(e["label"], e["id"]) for r in body.get("relationships") or [] for e in (r["source"], r["target"])]
        if any(end not in known for end in ends):  # as data: nothing is written (BatchError)
            return httpx.Response(422, json={"detail": "a relationship end doesn't exist"})
        self.batches.append(body)
        root = body.get("replace_from")
        if root:  # only the composition of the experiments (feature 055): what hangs from an experiment
            gone = self._descendants((root["label"], root["id"]))
            for key in gone:
                self.nodes.pop(key, None)
            self.links = {t for t in self.links if (t[1], t[2]) not in gone and (t[3], t[4]) not in gone}
        for node in nodes:
            key = (str(node["label"]), str(node["id"]))
            sent, mode, current = dict(node.get("properties") or {}), node.get("mode", "replace"), self.nodes.get(key)
            if mode == "ensure" and current is not None:
                continue
            merged = {**current, **sent} if mode == "merge" and current is not None else sent
            self.nodes[key] = {k: v for k, v in merged.items() if v is not None}
        for r in body.get("relationships") or []:
            source, target = r["source"], r["target"]
            self.links.add((r["type"], source["label"], source["id"], target["label"], target["id"]))
        return httpx.Response(200, json={"created": len(nodes)})

    COMPOSITION = frozenset(
        {"EXP_TIENE_DOCUMENTO", "EXP_TIENE_SECCION", "EXP_TIENE_CHUNK", "EXP_TIENE_VECTOR", "EXP_GENERA_VECTOR"}
    )

    def _descendants(self, owner: tuple[str, str]) -> set[tuple[str, str]]:
        found: set[tuple[str, str]] = set()
        frontier = [owner]
        while frontier:
            current = frontier.pop()
            for t in self.links:
                child = (t[3], t[4])
                if t[0] in self.COMPOSITION and (t[1], t[2]) == current and child not in found:
                    found.add(child)
                    frontier.append(child)
        return found

    def link(self, type: str, source: tuple[str, str], target: tuple[str, str]) -> None:
        self.links.add((type, source[0], source[1], target[0], target[1]))

    def _relationships(self, label: str, id: str) -> httpx.Response:
        if (label, id) not in self.nodes:
            return httpx.Response(404, json={"detail": "no node"})
        found = [
            {"type": t, "source": {"label": sl, "id": si}, "target": {"label": tl, "id": ti}, "properties": {}}
            for t, sl, si, tl, ti in sorted(self.links)
            if (sl, si) == (label, id) or (tl, ti) == (label, id)
        ]
        return httpx.Response(200, json=found)

    def _index(self, name: str, body: Json) -> httpx.Response:
        wanted = {"name": name, "label": body["label"], "property": body["property"], "dimensions": body["dimensions"]}
        if self.indexes.setdefault(name, wanted) != wanted:
            return httpx.Response(409, json={"detail": f"{name} already exists"})
        return httpx.Response(200, json=wanted)

    def _drop(self, name: str, drop: bool) -> httpx.Response:
        found = self.indexes.pop(name, None)
        self.dropped.append((name, drop))
        if found is None:
            return httpx.Response(404, json={"detail": "no index"})
        if drop:
            for key, properties in self.nodes.items():
                if key[0] == found["label"]:
                    properties.pop(str(found["property"]), None)
        return httpx.Response(204)

    def _missing(self, property: str) -> httpx.Response:
        """GET /data/progress/embeddings?list=missing (feature 057), one page with everything."""
        key = "huella_chunking_" + property
        found = sorted(
            id
            for (label, id), p in self.nodes.items()
            if label == "JSON"
            and p.get("estado_chunking") == "fragmentado"
            and (p.get(key) is None or p.get(key) != p.get("huella_chunking"))
        )
        return httpx.Response(200, json={"page": 1, "pages": 1, "sha256s": found})

    def _out(self, type: str, label: str, id: str) -> list[str]:
        return [t[4] for t in self.links if t[:3] == (type, label, id)]

    def _experiment_missing(self, experiment: str) -> httpx.Response:
        """GET /data/progress/experiment-embeddings?list=missing (feature 062), one page: the chunked EXP_DOCUMENTO of
        its chunking experiment with a chunk without its EXP_EMBED."""
        if ("EXP_EMBEDDINGS", experiment) not in self.nodes:
            return httpx.Response(404, json={"detail": "no embeddings experiment"})
        vectors = set(self._out("EXP_GENERA_VECTOR", "EXP_EMBEDDINGS", experiment))
        missing: list[str] = []
        for chunking in self._out("EXP_USA", "EXP_EMBEDDINGS", experiment):
            for document in self._out("EXP_TIENE_DOCUMENTO", "EXPERIMENTO", chunking):
                if self.nodes.get(("EXP_DOCUMENTO", document), {}).get("estado") != "fragmentado":
                    continue
                chunks = [
                    c
                    for s in self._out("EXP_TIENE_SECCION", "EXP_DOCUMENTO", document)
                    for c in self._out("EXP_TIENE_CHUNK", "EXP_SECCION", s)
                ]
                if any(not set(self._out("EXP_TIENE_VECTOR", "EXP_CHUNK", c)) & vectors for c in chunks):
                    missing.append(document.rsplit(":", 1)[-1])
        return httpx.Response(200, json={"page": 1, "pages": 1, "sha256s": sorted(missing)})

    def _parsed(self, request: httpx.Request) -> httpx.Response:
        """GET /data/progress/chunking?list=all (feature 059): the parsed JSON, a page at a time, by sha256."""
        page, per_page = int(request.url.params.get("page", "1")), int(request.url.params.get("per_page", "50"))
        found = sorted(
            id
            for (label, id), p in self.nodes.items()
            if label == "JSON" and p.get("estado") in ("parseado", "parcial")
        )
        chosen = found[(page - 1) * per_page : page * per_page]
        pages = -(-len(found) // per_page)
        return httpx.Response(200, json={"total": len(found), "page": page, "pages": pages, "sha256s": chosen})

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            return httpx.Response(503, json={"detail": "Neo4j doesn't answer"})
        parts = request.url.path.strip("/").split("/")
        if request.method == "POST" and parts == ["data", "batch"]:
            return self._batch(json.loads(request.content))
        if request.method == "PUT" and parts[:3] == ["data", "vectors", "indexes"] and len(parts) == 4:
            return self._index(parts[3], json.loads(request.content))
        if request.method == "DELETE" and parts[:3] == ["data", "vectors", "indexes"] and len(parts) == 4:
            return self._drop(parts[3], request.url.params.get("drop_property") == "true")
        if request.method == "GET" and parts == ["data", "progress", "chunking"]:
            return self._parsed(request)
        if request.method == "GET" and parts == ["data", "progress", "embeddings"]:
            return self._missing(request.url.params.get("property", ""))
        if request.method == "GET" and parts == ["data", "progress", "experiment-embeddings"]:
            return self._experiment_missing(request.url.params.get("experiment", ""))
        if request.method == "GET" and parts[:2] == ["data", "nodes"] and len(parts) == 5:
            return self._relationships(parts[2], parts[3])
        if request.method == "DELETE" and parts[:2] == ["data", "nodes"] and len(parts) == 4:
            if self.nodes.pop((parts[2], parts[3]), None) is None:
                return httpx.Response(404, json={"detail": "no node"})
            self.links = {r for r in self.links if (parts[2], parts[3]) not in ((r[1], r[2]), (r[3], r[4]))}
            return httpx.Response(204)
        if request.method == "GET" and parts[:2] == ["data", "nodes"] and len(parts) == 3:
            return self._page(parts[2], request)
        if request.method == "GET" and parts[:2] == ["data", "nodes"] and len(parts) == 4:
            found = self.nodes.get((parts[2], parts[3]))
            if found is None:
                return httpx.Response(404, json={"detail": "no node"})
            omit = set(request.url.params.get_list("omit"))
            properties = {k: v for k, v in found.items() if k not in omit}
            return httpx.Response(200, json={"label": parts[2], "id": parts[3], "properties": properties})
        return httpx.Response(404, json={"detail": f"no route {request.url.path}"})

    def client(self) -> httpx.Client:
        return httpx.Client(base_url="http://server", transport=httpx.MockTransport(self.handle))


# embeddings (feature 046): its ports in memory, for the domain and the routes.


class FakeEmbedder:
    """`tokens` = words + 2 (the special tokens); a vector is [words, 1.0]. `down`: the model can't be loaded."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], int]] = []
        self.down = False
        self.installed = True

    def available(self) -> bool:
        return self.installed

    def _check(self) -> None:
        if self.down:
            raise UpstreamDown("the model can't be loaded")

    def embed(self, model: str, texts: list[str], max_tokens: int) -> list[list[float]]:
        self._check()
        self.calls.append((model, texts, max_tokens))
        return [[float(len(t.split())), 1.0] for t in texts]

    def tokens(self, model: str, text: str) -> int:
        self._check()
        return len(text.split()) + 2

    def prefix_tokens(self, model: str) -> int | None:
        """The words of the model's passage prefix, as LocalModels: 0 without one, None if it has one and the extra
        isn't installed (`installed` False)."""
        spec = MODELS.get(model)
        prefix = spec.passage_prefix if spec is not None else ""
        if not prefix:
            return 0
        return len(prefix.split()) if self.installed else None


class FakeChunkSource:
    """ChunkSource in memory: `documents`, `chunks_of` (sha256 → chunks), `experiments` (id → status) and
    `experiment_of` (id → sha256 → chunks). `down`: data doesn't answer."""

    def __init__(self) -> None:
        self.documents: dict[str, EmbeddableDocument] = {}
        self.chunks_of: dict[str, list[EmbeddableChunk]] = {}
        self.experiments: dict[str, str] = {}
        self.experiment_of: dict[str, dict[str, list[EmbeddableChunk]]] = {}
        self.experiment_reads: list[str] = []  # the documents whose experiment chunks were read, in order (059)
        self.asked_missing: list[tuple[str, int | None, int | None]] = []
        self.missing_of: dict[str, list[str]] = {}  # embeddings experiment → documents without its vectors (062)
        self.down = False

    def add(
        self,
        sha256: str,
        texts: list[str],
        chunked: bool = True,
        fingerprints: dict[str, str] | None = None,
        chunking: str | None = None,
        embedded_over: dict[str, str] | None = None,
    ) -> None:
        self.documents[sha256] = EmbeddableDocument(sha256, chunked, fingerprints or {}, chunking, embedded_over or {})
        self.chunks_of[sha256] = [EmbeddableChunk(f"{sha256}:{k}", text) for k, text in enumerate(texts)]

    def _check(self) -> None:
        if self.down:
            raise UpstreamDown("data doesn't answer")

    def document(self, sha256: str) -> EmbeddableDocument | None:
        self._check()
        return self.documents.get(sha256)

    def chunks(self, sha256: str) -> list[EmbeddableChunk]:
        self._check()
        return list(self.chunks_of.get(sha256, []))

    def missing(self, property: str, page: int | None, per_page: int | None) -> list[str]:
        """What data would say is missing: the chunked documents whose mark isn't their huella_chunking."""
        self._check()
        self.asked_missing.append((property, page, per_page))
        key = "huella_chunking_" + property
        found = sorted(
            s
            for s, d in self.documents.items()
            if d.chunked and (d.chunking is None or d.embedded_over.get(key) != d.chunking)
        )
        if page is None:
            return found
        size = per_page or len(found) or 1
        return found[(page - 1) * size : page * size]

    def experiment_status(self, experiment: str) -> str | None:
        return self.experiments.get(experiment)

    def experiment_documents(self, experiment: str) -> list[str]:
        self._check()
        return sorted(self.experiment_of.get(experiment, {}))

    def experiment_document_chunks(self, experiment: str, sha256: str) -> list[EmbeddableChunk]:
        self._check()
        self.experiment_reads.append(sha256)
        return list(self.experiment_of.get(experiment, {}).get(sha256, []))

    def experiment_missing(self, embeddings_experiment: str) -> list[str] | None:
        """Feature 062: `missing_of` (embeddings experiment → what it lacks); None if it isn't there."""
        self._check()
        found = self.missing_of.get(embeddings_experiment)
        return None if found is None else list(found)

    def fingerprint_counts(self) -> dict[str, int]:
        self._check()
        return dict(Counter(key for d in self.documents.values() for key in d.fingerprints))

    def with_fingerprint(self, key: str) -> list[str]:
        self._check()
        return sorted(sha256 for sha256, d in self.documents.items() if key in d.fingerprints)


class FakeVectorSink:
    """VectorSink and ConfigStore in memory: the indexes asked for, the batches saved and the active configuration.
    A batch with a node of `refuse` is refused (DocumentError)."""

    def __init__(self) -> None:
        self.indexes: list[VectorIndexSpec] = []
        self.batches: list[GraphBatch] = []
        self.refuse: set[str] = set()
        self.stored: EmbeddingConfig | None = None
        self.dropped: list[tuple[str, bool]] = []

    def ensure_index(self, index: VectorIndexSpec) -> None:
        self.indexes.append(index)

    def drop_index(self, name: str, drop_property: bool) -> bool:
        self.dropped.append((name, drop_property))
        return any(index.name == name for index in self.indexes)

    def save(self, batch: GraphBatch) -> None:
        if any(node.key.id in self.refuse for node in batch.nodes):
            raise DocumentError("data refused it")
        self.batches.append(batch)

    def active(self) -> EmbeddingConfig | None:
        return self.stored

    def set(self, config: EmbeddingConfig) -> None:
        self.stored = config

    def clear(self) -> bool:
        found, self.stored = self.stored is not None, None
        return found


def chunked_document(
    data: FakeData, sha256: str, sections: list[list[str]], experiment: str | None = None, state: str = "fragmentado"
) -> list[str]:
    """Puts in `data` what chunking leaves: JSON → SECCION → FRAGMENTOS or, with `experiment`, EXPERIMENTO →
    EXP_SECCION → EXP_CHUNK, with these texts per section (stored out of order: the source orders them). The ids of
    the chunks, in order."""
    root: tuple[str, str]
    if experiment is None:
        data.nodes[("JSON", sha256)] = {"estado": "parseado", "estado_chunking": state, "documento": "big"}
        root, labels, relations, prefix = (
            ("JSON", sha256),
            ("SECCION", "FRAGMENTOS"),
            ("TIENE_SECCION", "TIENE_FRAGMENTO"),
            sha256,
        )
    else:
        data.nodes.setdefault(("EXPERIMENTO", experiment), {"estado": "finished"})
        root = ("EXP_DOCUMENTO", f"{experiment}:{sha256}")  # feature 055 part b
        data.nodes[root] = {"sha256": sha256, "estado": "fragmentado"}
        data.link("EXP_TIENE_DOCUMENTO", ("EXPERIMENTO", experiment), root)
        labels = ("EXP_SECCION", "EXP_CHUNK")
        relations, prefix = ("EXP_TIENE_SECCION", "EXP_TIENE_CHUNK"), f"{experiment}:{sha256}"
    starts = [sum(len(t) for t in sections[:order]) for order in range(len(sections))]
    for order in reversed(range(len(sections))):
        section = (labels[0], f"{prefix}:s{order}")
        data.nodes[section] = {"orden": order, "encabezados": [f"t{order}"], "sha256": sha256}
        data.link(relations[0], root, section)
        for offset, text in reversed(list(enumerate(sections[order]))):
            k = starts[order] + offset
            chunk = (labels[1], f"{prefix}:{k}")
            data.nodes[chunk] = {"indice": k, "texto": text, "texto_contextualizado": f"t{order}\n{text}"}
            data.link(relations[1], section, chunk)
    return [f"{prefix}:{k}" for k in range(sum(len(t) for t in sections))]


# llm (feature 047): Ollama's HTTP API over a dict, as an httpx.MockTransport.


class FakeOllama:
    """Ollama's /api/version, /api/tags, /api/pull (NDJSON lines), /api/delete and /api/chat. `models`: name → size;
    `down`: every request fails to connect; `chats`: every body of /api/chat; `pull_error`: the error line a pull
    answers; `failure`: the status every request answers (500: Ollama broke, 400: it refused it)."""

    VERSION = "0.12.0"

    def __init__(self) -> None:
        self.models: dict[str, int] = {}
        self.down = False
        self.chats: list[Json] = []
        self.pull_error: str | None = None
        self.failure: int | None = None

    def _pull(self, name: str) -> httpx.Response:
        if self.pull_error is not None:
            return httpx.Response(200, content=json.dumps({"error": self.pull_error}).encode())
        lines = [
            {"status": "pulling manifest"},
            {"status": "pulling abc", "completed": 50, "total": 100},
            {"status": "pulling abc", "completed": 100, "total": 100},
            {"status": "verifying sha256 digest"},
            {"status": "success"},
        ]
        self.models[name] = 100
        return httpx.Response(200, content="\n".join(json.dumps(line) for line in lines).encode())

    def _chat(self, body: Json) -> httpx.Response:
        self.chats.append(body)
        model = str(body["model"])
        if model not in self.models:
            return httpx.Response(404, json={"error": f'model "{model}" not found, try pulling it first'})
        answer = {
            "model": model,
            "message": {"role": "assistant", "content": f"eco: {body['messages'][-1]['content']}"},
            "done": True,
            "total_duration": 1_500_000_000,
            "prompt_eval_count": 12,
            "eval_count": 3,
        }
        return httpx.Response(200, json=answer)

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("connection refused", request=request)
        if self.failure is not None:
            return httpx.Response(self.failure, json={"error": "it broke"})
        route = (request.method, request.url.path)
        if route == ("GET", "/api/version"):
            return httpx.Response(200, json={"version": self.VERSION})
        if route == ("GET", "/api/tags"):
            models = [
                {"name": n, "size": s, "modified_at": "2026-11-01T10:00:00Z", "details": {"family": n.split(":")[0]}}
                for n, s in sorted(self.models.items())
            ]
            return httpx.Response(200, json={"models": models})
        body: Json = json.loads(request.content) if request.content else {}
        if route == ("POST", "/api/pull"):
            return self._pull(str(body["model"]))
        if route == ("DELETE", "/api/delete"):
            if self.models.pop(str(body["model"]), None) is None:
                return httpx.Response(404, json={"error": "model not found"})
            return httpx.Response(200)
        if route == ("POST", "/api/chat"):
            return self._chat(body)
        return httpx.Response(404, json={"error": f"no route {request.url.path}"})

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)
