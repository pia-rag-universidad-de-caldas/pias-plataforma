"""Evaluate a pipeline laboratory iteration and answer its review through the public APIs.

Run with ``python src/labs/lab2/evaluator.py`` while the server is running. The actor reads the
waiting laboratory iteration from ``/pipeline/inbox``, loads its chunks through ``/data``, and
posts an approve/retry decision to the answer route supplied by the pipeline.
"""

from __future__ import annotations

import argparse
import time
from collections import Counter
from typing import Any, cast
from urllib.parse import quote

import httpx  # noqa: TID251 - the lab is an external pipeline actor, not a work module

BASE_URL = "http://127.0.0.1:8000"
ACTOR = "lab"
MAX_TOKENS_DEFAULT = 126
ACCEPTANCE_SCORE = 4.0
MIN_ACCEPTED_CHUNK_RATIO = 0.95
DATA_PATH = "/data"
PIPELINE_PATH = "/pipeline"


def _url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def evaluate_integrity(text: str) -> dict[str, object]:
    clean_text = text.strip()
    issues = ["empty_chunk"] if not clean_text else []
    return {
        "valid": not issues,
        "characters": len(clean_text),
        "words": len(clean_text.split()),
        "issues": issues,
    }


def evaluate_length(token_count: int | None, max_tokens: int) -> dict[str, object]:
    issues: list[str] = []
    if token_count is None or token_count <= 0:
        issues.append("missing_or_empty_token_count")
    elif token_count > max_tokens:
        issues.append("max_tokens_exceeded")
    return {
        "valid": not issues,
        "token_count": token_count,
        "max_tokens": max_tokens,
        "issues": issues,
    }


def evaluate_duplicates(texts: list[object]) -> dict[str, object]:
    normalized = [text.strip().casefold() for text in texts if isinstance(text, str) and text.strip()]
    counts = Counter(normalized)
    duplicates = {text: count for text, count in counts.items() if count > 1}
    duplicate_chunks = sum(count - 1 for count in duplicates.values())
    return {
        "total_chunks": len(texts),
        "duplicated_chunks": duplicate_chunks,
        "duplicate_ratio": duplicate_chunks / len(texts) if texts else 0.0,
        "duplicates": duplicates,
    }


def evaluate_chunk(chunk: dict[str, object], max_tokens: int) -> dict[str, object]:
    raw_text = chunk.get("texto_contextualizado", chunk.get("contextualized_text"))
    text = raw_text if isinstance(raw_text, str) else ""
    raw_tokens = chunk.get("tokens")
    token_count = raw_tokens if isinstance(raw_tokens, int) and not isinstance(raw_tokens, bool) else None
    integrity = evaluate_integrity(text)
    length = evaluate_length(token_count, max_tokens)
    return {
        "id": chunk.get("id"),
        "index": chunk.get("indice", chunk.get("index")),
        "valid": bool(integrity["valid"] and length["valid"]),
        "chunk_integrity": integrity,
        "chunk_text_length": length,
    }


def evaluate_document(chunks: list[dict[str, object]], max_tokens: int) -> dict[str, object]:
    results = [evaluate_chunk(chunk, max_tokens) for chunk in chunks]
    texts = [chunk.get("texto_contextualizado", chunk.get("contextualized_text")) for chunk in chunks]
    duplicates = evaluate_duplicates(texts)
    duplicate_map = duplicates["duplicates"]
    duplicate_texts = set(duplicate_map) if isinstance(duplicate_map, dict) else set()
    seen: set[str] = set()
    for result, raw_text in zip(results, texts, strict=True):
        normalized = raw_text.strip().casefold() if isinstance(raw_text, str) else ""
        duplicate = normalized in duplicate_texts and normalized in seen
        if normalized:
            seen.add(normalized)
        result["duplicate"] = duplicate
        result["score"] = 5.0 if result["valid"] and not result["duplicate"] else 0.0

    total = len(results)
    valid_count = sum(bool(result["valid"]) for result in results)
    valid_ratio = valid_count / total if total else 0.0
    raw_duplicate_ratio = duplicates["duplicate_ratio"]
    duplicate_ratio = float(raw_duplicate_ratio) if isinstance(raw_duplicate_ratio, int | float) else 0.0
    score = round(5.0 * max(0.0, valid_ratio - duplicate_ratio), 2)
    return {
        "total_chunks": total,
        "count_valid_chunks": valid_count,
        "chunk_duplicated": duplicates,
        "valid_ratio": valid_ratio,
        "score": score,
        "accepted": score >= ACCEPTANCE_SCORE and valid_ratio >= MIN_ACCEPTED_CHUNK_RATIO,
        "chunk_results": results,
    }


def _get_json(client: httpx.Client, base_url: str, path: str) -> Any:  # noqa: ANN401 - API payloads are runtime JSON
    response = client.get(_url(base_url, path))
    response.raise_for_status()
    return cast(object, response.json())


def get_experiment_chunks(
    experiment_id: str, sha256: str | None = None, *, base_url: str = BASE_URL, client: httpx.Client | None = None
) -> list[dict[str, object]]:
    """Read an experiment's chunks through data's node and relationship endpoints."""
    own_client = client is None
    session = client or httpx.Client(timeout=30.0)
    try:
        exp_id = quote(experiment_id, safe="")
        sections = _get_json(session, base_url, f"{DATA_PATH}/nodes/EXPERIMENTO/{exp_id}/relationships")
        section_ids = sorted(
            relation["target"]["id"]
            for relation in sections
            if relation.get("type") == "EXP_GENERA"
            and relation.get("source", {}).get("id") == experiment_id
            and relation.get("target", {}).get("label") == "EXP_SECCION"
        )
        found: list[dict[str, object]] = []
        for section_id in section_ids:
            links = _get_json(
                session,
                base_url,
                f"{DATA_PATH}/nodes/EXP_SECCION/{quote(section_id, safe='')}/relationships",
            )
            chunk_ids = sorted(
                relation["target"]["id"]
                for relation in links
                if relation.get("type") == "EXP_TIENE_CHUNK"
                and relation.get("source", {}).get("id") == section_id
                and relation.get("target", {}).get("label") == "EXP_CHUNK"
            )
            for chunk_id in chunk_ids:
                if sha256 is not None and not chunk_id.startswith(f"{experiment_id}:{sha256}:"):
                    continue
                node = _get_json(
                    session,
                    base_url,
                    f"{DATA_PATH}/nodes/EXP_CHUNK/{quote(chunk_id, safe='')}",
                )
                properties = node.get("properties", {})
                found.append({"id": chunk_id, **properties})
        return sorted(
            found,
            key=lambda chunk: (
                chunk.get("indice") if isinstance(chunk.get("indice"), int) else 0,
                str(chunk.get("id", "")),
            ),
        )
    finally:
        if own_client:
            session.close()


def _iteration_config(item: dict[str, Any], *, base_url: str, client: httpx.Client) -> dict[str, Any]:
    run_id = quote(str(item["run"]), safe="")
    run = _get_json(client, base_url, f"{PIPELINE_PATH}/runs/{run_id}")
    wanted_index = item.get("iteration")
    wanted_stage = item.get("stage")
    for iteration in run.get("iterations", []):
        if iteration.get("index") == wanted_index and iteration.get("stage") == wanted_stage:
            return cast(dict[str, Any], iteration.get("config", {}))
    raise ValueError(f"No encuentro la configuración de la iteración {wanted_index} de {wanted_stage!r}")


def _retry_configuration(config: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    chunking = config.get("chunking", {})
    current = str(chunking.get("chunker", "hybrid"))
    alternatives = ("hybrid", "hierarchical", "page")
    next_chunker = (
        alternatives[(alternatives.index(current) + 1) % len(alternatives)] if current in alternatives else "hybrid"
    )
    next_chunking: dict[str, object] = {"chunker": next_chunker}
    too_long = False
    chunk_results = evaluation.get("chunk_results", [])
    if isinstance(chunk_results, list):
        for result in chunk_results:
            if not isinstance(result, dict):
                continue
            length = result.get("chunk_text_length")
            issues = length.get("issues") if isinstance(length, dict) else None
            if isinstance(issues, list) and "max_tokens_exceeded" in issues:
                too_long = True
                break
    if too_long:
        current_max = chunking.get("max_tokens", MAX_TOKENS_DEFAULT)
        if isinstance(current_max, int) and not isinstance(current_max, bool) and current_max > 16:
            next_chunking["max_tokens"] = max(16, int(current_max * 0.8))
            next_chunking["chunker"] = "hybrid"
    return {"chunking": next_chunking}


def process_inbox_item(item: dict[str, Any], *, base_url: str = BASE_URL) -> dict[str, Any]:
    if not isinstance(item.get("experiment"), str) or not isinstance(item.get("answer"), str):
        raise ValueError("La bandeja no incluye el experimento de chunking y su ruta de respuesta")
    if item.get("exhausted"):
        raise ValueError(f"La corrida {item.get('run')} agotó sus iteraciones; requiere aprobación manual")

    with httpx.Client(timeout=60.0) as client:
        config = _iteration_config(item, base_url=base_url, client=client)
        chunking = config.get("chunking", {})
        max_tokens = chunking.get("max_tokens", MAX_TOKENS_DEFAULT)
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool):
            max_tokens = MAX_TOKENS_DEFAULT
        chunks = get_experiment_chunks(str(item["experiment"]), base_url=base_url, client=client)
        evaluation = evaluate_document(chunks, max_tokens)
        decision = "approve" if evaluation["accepted"] else "retry"
        duplicate_info = evaluation["chunk_duplicated"]
        duplicate_ratio = duplicate_info.get("duplicate_ratio", 0.0) if isinstance(duplicate_info, dict) else 0.0
        score: dict[str, object] = {
            "score": evaluation["score"],
            "criteria": {
                "valid_chunk_ratio": evaluation["valid_ratio"],
                "min_valid_chunk_ratio": MIN_ACCEPTED_CHUNK_RATIO,
                "duplicate_ratio": duplicate_ratio,
                "acceptance_score": ACCEPTANCE_SCORE,
                "chunks": evaluation["chunk_results"],
            },
            "author": ACTOR,
            "comment": "Evaluación automática de integridad, longitud y duplicados por chunk.",
        }
        body: dict[str, object] = {"decision": decision, "actor": ACTOR, "score": score}
        if decision == "retry":
            body["next"] = _retry_configuration(config, evaluation)
        response = client.post(_url(base_url, str(item["answer"])), json=body)
        response.raise_for_status()
        return {"run": item["run"], "iteration": item.get("iteration"), **evaluation, "decision": decision}


def evaluate_pending(*, base_url: str = BASE_URL, actor: str = ACTOR) -> list[dict[str, Any]]:
    with httpx.Client(timeout=30.0) as client:
        inbox = _get_json(client, base_url, f"{PIPELINE_PATH}/inbox?actor={quote(actor, safe='')}")
    return [process_inbox_item(item, base_url=base_url) for item in inbox]


def main() -> int:
    parser = argparse.ArgumentParser(description="Evalúa y responde iteraciones pendientes del laboratorio PIAA.")
    parser.add_argument("--base-url", default=BASE_URL, help="URL raíz del servidor (default: %(default)s)")
    parser.add_argument("--actor", default=ACTOR, help="actor del pipeline (default: %(default)s)")
    parser.add_argument("--watch", action="store_true", help="seguir consultando la bandeja hasta interrumpir")
    parser.add_argument("--poll-seconds", type=float, default=3.0, help="espera entre consultas con --watch")
    args = parser.parse_args()

    while True:
        for result in evaluate_pending(base_url=args.base_url, actor=args.actor):
            print(result)
        if not args.watch:
            return 0
        time.sleep(max(0.25, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
