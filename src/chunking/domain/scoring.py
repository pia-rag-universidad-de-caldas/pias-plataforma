"""Scoring: checks and summarizes the scores of experiments, and puts experiments side by side (feature 025)."""

import math

from chunking.config import SCORE_CRITERIA, SCORE_MAX, SCORE_MIN
from chunking.models import (
    ComparedExperiment,
    ExperimentRecord,
    ExperimentResults,
    KeyResults,
    Score,
    ScoreSummary,
    TokenStats,
)

from .parameters import InvalidParameters


def token_stats(values: list[int]) -> TokenStats | None:
    if not values:
        return None
    ordered = sorted(values)
    p90 = ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)]
    return TokenStats(ordered[0], round(sum(ordered) / len(ordered), 1), p90, ordered[-1])


class Scoring:
    @staticmethod
    def check(criteria: dict[str, float]) -> None:
        """InvalidParameters if a criterion has an empty name or a value out of SCORE_MIN–SCORE_MAX."""
        for name, value in criteria.items():
            if not name.strip():
                raise InvalidParameters("a criterion needs a name")
            if not SCORE_MIN <= value <= SCORE_MAX:
                raise InvalidParameters(f"criterion {name!r}: {value} is out of {SCORE_MIN}–{SCORE_MAX}")

    @staticmethod
    def summary(scores: list[Score]) -> ScoreSummary:
        names = list(dict.fromkeys([*SCORE_CRITERIA, *(n for s in scores for n in s.criteria)]))
        averages: dict[str, float | None] = {}
        for name in names:
            values = [s.criteria[name] for s in scores if name in s.criteria]
            averages[name] = round(sum(values) / len(values), 3) if values else None
        every = [v for s in scores for v in s.criteria.values()]
        overall = round(sum(every) / len(every), 3) if every else None
        return ScoreSummary(len(scores), averages, overall)

    @staticmethod
    def key_results(results: ExperimentResults | None, tokens: list[int] | None = None) -> KeyResults | None:
        if results is None:
            return None
        groups = results.by_strategy.values()
        weighted = [g for g in groups if g.tokens is not None]
        stats = None
        if weighted:  # combined from the per-strategy stats (min, max exact; mean weighted; p90 the largest p90)
            chunks = sum(g.chunks for g in weighted)
            mean = sum(g.tokens.mean * g.chunks for g in weighted if g.tokens) / chunks if chunks else 0.0
            stats = TokenStats(
                min(g.tokens.min for g in weighted if g.tokens),
                round(mean, 1),
                max(g.tokens.p90 for g in weighted if g.tokens),
                max(g.tokens.max for g in weighted if g.tokens),
            )
        return KeyResults(
            documents=results.documents,
            converted=results.converted,
            reused=results.reused,
            errors=results.errors,
            sections=sum(g.sections for g in groups),
            chunks=sum(g.chunks for g in groups),
            tokens=token_stats(tokens) if tokens else stats,
        )

    @staticmethod
    def compare(record: ExperimentRecord, scores: list[Score]) -> ComparedExperiment:
        return ComparedExperiment(
            id=record.id,
            name=record.name,
            status=record.status,
            conversion_json=record.conversion_json,
            plan_json=record.plan_json,
            scores=scores,
            summary=Scoring.summary(scores),
            results=Scoring.key_results(record.results),
        )
