from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from chunking.adapters.strategies.tools import Models

import httpx

BASE_URL = "http://127.0.0.1:8000/chunking"
MAX_TOKENS_DEFAULT = 126
ACCEPTANCE_SCORE = 4.0
MIN_ACCEPTED_CHUNK_RATIO = 0.95

def evaluate_integrity(text: str) -> dict[str, object]:
    clean_text = text.strip()
    issues = []

    if not clean_text:
        issues.append("empty_chunk")

    return {
        "valid": len(issues) == 0,
        "characters": len(clean_text),
        "words": len(clean_text.split()),
        "issues": issues
    }

models = Models()

def evaluate_length(text: str, tokenizer_name: str, max_tokens: int) -> dict[str, object]:
    tokens = models.tokens(tokenizer_name)
    clean_text = text.strip()
    issues = []
    token_count = tokens.count(clean_text)
    if token_count == 0:
        issues.append("empty_chunk")
    elif token_count > max_tokens:
        issues.append("max_tokens_exceeded")

    return {
        "valid": len(issues) == 0,
        "token_count": token_count,
        "max_tokens": max_tokens,
        "issues": issues
    }

def evaluate_duplicates(texts: list[str]) -> dict[str, object]:
    if not texts:
        return {
        "total_chunks": 0,
        "duplicated_chunks": 0,
        "duplicate_ratio": 0,
        "duplicates": {}
    }

    normalized = [text.strip().casefold() for text in texts if isinstance(text, str) and text.strip()]
    counter = Counter(normalized)

    duplicated = {text: count for text, count in counter.items() if count >= 2}
    duplicated_chunks = sum(count - 1 for count in duplicated.values())
    total_chunks = len(texts)
    duplicate_ratio = duplicated_chunks / total_chunks if total_chunks else 0
    return {
        "total_chunks": total_chunks,
        "duplicated_chunks": duplicated_chunks,
        "duplicate_ratio": duplicate_ratio,
        "duplicates": duplicated
    }

def evaluate_chunk(chunk: dict[str, object], tokenizer_name: str, max_tokens: int) -> dict[str, object]:
    chunk_text = chunk.get("contextualized_text")
    if isinstance(chunk_text, str):
        chunk_integrity = evaluate_integrity(chunk_text)
        chunk_text_length = evaluate_length(chunk_text, tokenizer_name, max_tokens)
        if chunk_integrity["valid"] and chunk_text_length["valid"]:
            valid = True
        else:
            valid = False
    else:
        valid = False
        return {
                "index": chunk.get("index"),
                "valid": valid,
                "chunk_integrity": {},
                "chunk_text_length": {}
            }

    return {
        "index": chunk.get("index"),
        "valid": valid,
        "chunk_integrity": chunk_integrity,
        "chunk_text_length": chunk_text_length
    }

def evaluate_document(chunks: list[dict[str, object]], tokenizer_name: str, max_tokens: int) -> dict[str, object]:
    list_chunks = []
    for c in chunks:
        list_chunks.append(evaluate_chunk(c, tokenizer_name, max_tokens))

    chunk_text = []
    for chunk in chunks:
        chunk_text.append(chunk.get("contextualized_text"))

    chunk_duplicated = evaluate_duplicates(chunk_text)

    count_valid_chunks = 0
    for chunk in list_chunks:
        if chunk["valid"]:
            count_valid_chunks += 1
    total_chunks = len(list_chunks)
    valid_ratio = count_valid_chunks / total_chunks if total_chunks else 0

    return {
        "total_chunks": total_chunks,
        "count_valid_chunks": count_valid_chunks,
        "chunk_duplicated": chunk_duplicated,
        "valid_ratio": valid_ratio,
        "chunk_results": list_chunks
    }

def get_experiment_chunks(experiment_id: str, sha256: str):
    route = f"{BASE_URL}/experiments/phase/02/{experiment_id}/documents/{sha256}/chunks"
    response = httpx.get(route)
    response.raise_for_status()
    return response.json()

def save_experiment_scores(experiment_id: str, scores: dict):
    route = f"{BASE_URL}/experiments/phase/02/{experiment_id}/scores"
    response = httpx.post(route, json=scores)
    response.raise_for_status()
    return response.json()