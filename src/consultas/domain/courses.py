"""Which courses a question names (feature 057), from the candidates data's full-text search gives.

A chunk of a PIAA doesn't say which course it is about (only its header does), so "¿qué evalúa Psicología de la
percepción?" would find the evaluation of any course. When the question names a course, the search goes only over
that course's documents (every version of its PIAA). Lucene's score can't say whether a course is named (it is only
comparable within one answer), so the rule is consultas': the words of the course's name that the question has.

- A code of the course (0100105, G6K0346) in the question names it.
- A name is named when the question has at least MIN_COVERAGE of its words (without "de", "la"...), and of the named
  ones only those with the most words in the question stay ("Historia del arte IV" wins over "Historia").
- A name of one word ("Estadística") is too common a word: it names a course only with a cue ("curso", "asignatura",
  "materia", "PIAA"...) in the question.

Within the named course its name is in front of every chunk (embeddings puts it there), so it no longer tells
chunks apart: what does is the rest of the question, its topic ("evalúa", "bibliografía"). `rerank` orders the
course's chunks by their cosine plus a bonus for each word of the topic they have (by its root: "evalúa" is in
"CRITERIOS DE EVALUACIÓN"), and leaves a repeated text once.

Only text rules: no I/O."""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from consultas.config import (
    COURSE_CUES,
    LEXICAL_WEIGHT,
    MIN_COVERAGE,
    ROOT,
    SECTION_SYNONYMS,
    STOP_WORDS,
    TEXT_SHARE,
)
from consultas.models import CourseMatch, Source

_WORD = re.compile(r"\w+")


def fold(text: str) -> str:
    """Lowercase and without accents."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))


def _stem(word: str) -> str:
    """A light plural: "evaluaciones" and "evaluacion" are the same word."""
    for ending in ("es", "s"):
        if len(word) > 4 and word.endswith(ending):
            return word[: -len(ending)]
    return word


def words(text: str) -> set[str]:
    """The words that tell something: folded, stemmed and without stop words."""
    return {_stem(w) for w in _WORD.findall(fold(text)) if w not in STOP_WORDS}


@dataclass(frozen=True)
class _Scored:
    match: CourseMatch
    matched: int  # words of its name in the question (or, by its code, all of them)


def _scored(match: CourseMatch, question: set[str], all_words: set[str], cue: bool) -> _Scored | None:
    if match.activity_code and fold(match.activity_code) in all_words:
        return _Scored(match, len(words(match.name or "")) + 1)
    name = words(match.name or "")
    if not name:
        return None
    found = len(name & question)
    if found / len(name) < MIN_COVERAGE or (len(name) == 1 and not cue):
        return None
    return _Scored(match, found)


def named(question: str, candidates: Sequence[CourseMatch]) -> list[CourseMatch]:
    """The candidates the question names (every document of the course: each version of its PIAA); [] if none."""
    folded = _WORD.findall(fold(question))
    found = words(question)
    cue = any(w in COURSE_CUES for w in folded)
    scored = [s for s in (_scored(c, found, set(folded), cue) for c in candidates) if s is not None]
    if not scored:
        return []
    best = max(s.matched for s in scored)
    return [s.match for s in scored if s.matched == best]


def topic(question: str, courses: Sequence[CourseMatch]) -> set[str]:
    """The words of the question that aren't the named courses' names or codes, nor a cue ("curso")."""
    named_words = set().union(*(words(c.name or "") for c in courses)) if courses else set()
    codes = {fold(c.activity_code) for c in courses if c.activity_code}
    return {w for w in words(question) if w not in named_words and w not in codes and w not in COURSE_CUES}


def _root(word: str) -> str:
    return word[:ROOT]


def rerank(sources: Sequence[Source], topic_words: set[str], k: int) -> list[Source]:
    """The best `k`: cosine plus LEXICAL_WEIGHT times the share of the topic's words the chunk (its headings and
    text) has, compared by their root or the other names of a section (SECTION_SYNONYMS), a word of its headings
    weighing more than one of its text; a text already chosen isn't repeated. The scores stay the cosine."""
    wanted = [{_root(w), *SECTION_SYNONYMS.get(_root(w), ())} for w in topic_words]

    def bonus(source: Source) -> float:
        """A word in the chunk's headings (the section it is in) counts whole; only in its text, TEXT_SHARE."""
        if not wanted:
            return 0.0
        headings = {_root(w) for w in words(" ".join(source.headings))}
        text = {_root(w) for w in words(source.text)}
        found = sum(1.0 if roots & headings else TEXT_SHARE if roots & text else 0.0 for roots in wanted)
        return LEXICAL_WEIGHT * found / len(wanted)

    chosen: list[Source] = []
    seen: set[str] = set()
    for source in sorted(sources, key=lambda s: s.score + bonus(s), reverse=True):
        text = " ".join(source.text.split())
        if text in seen:
            continue
        seen.add(text)
        chosen.append(source)
        if len(chosen) == k:
            break
    return chosen
