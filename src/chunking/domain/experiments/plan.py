"""Planner: which rule of an experiment's plan takes each section of a document (feature 025). Rules are tried in
order and the first that matches wins; the sections none takes get the plan's default."""

import unicodedata

from chunking.models import ConvertedDocument, DocumentSection, Match, Plan, SectionAssignment

from .parameters import InvalidParameters


class Planner:
    @staticmethod
    def normalize(text: str) -> str:
        """Lowercase, without accents and with single spaces: "Justificación" and "JUSTIFICACION" match."""
        decomposed = unicodedata.normalize("NFKD", text.casefold())
        return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())

    @staticmethod
    def check(match: Match) -> None:
        """InvalidParameters if a rule's match can't take anything or its position isn't a stretch of 0–1."""
        if not any(t.strip() for t in match.titles) and match.position is None:
            raise InvalidParameters("a rule needs `titles` (not empty) or `position`")
        if match.position is not None and not 0 <= match.position.start <= match.position.end <= 1:
            raise InvalidParameters("`position` needs 0 <= from <= to <= 1")

    @staticmethod
    def position(index: int, total: int) -> float:
        """Where a section is in the document: the middle of its stretch (of `total` equal ones), 0–1."""
        return (index + 0.5) / total

    @staticmethod
    def matches(match: Match, section: DocumentSection, position: float) -> bool:
        if match.titles:
            title = Planner.normalize(section.title)
            if not any(Planner.normalize(word) in title for word in match.titles if word.strip()):
                return False
        return match.position is None or match.position.start <= position <= match.position.end

    @staticmethod
    def assign(document: ConvertedDocument, plan: Plan) -> list[SectionAssignment]:
        total = len(document.sections)
        assignments: list[SectionAssignment] = []
        for index, section in enumerate(document.sections):
            where = Planner.position(index, total)
            rule = next((i for i, r in enumerate(plan.rules) if Planner.matches(r.match, section, where)), None)
            parameters = plan.default if rule is None else plan.rules[rule].chunking
            assignments.append(SectionAssignment(index, section, rule, parameters))
        return assignments
