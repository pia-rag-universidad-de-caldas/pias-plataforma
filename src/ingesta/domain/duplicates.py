"""Duplicate-by-content rules.

- Two files are duplicates if they have the same sha256.
- Empty files (0 B) don't count: they all share the hash and would form a false group.
- In each group, the original (the one that stays) is the last modified one; the rest are copies.
"""

from collections import defaultdict
from collections.abc import Iterable

from ingesta.models import DuplicateGroup, DuplicatesSummary, FileRecord, NewDuplicate
from ingesta.utils import NaturalKey, natural_key

# (unknown year, year, month number, week, target)
AgeKey = tuple[bool, int, int, NaturalKey, str]
# (modified, year, month number, week, origin)
NewnessKey = tuple[str, int, int, NaturalKey, str]


class Duplicates:
    """Only static methods: groups the duplicate rules under one name."""

    @staticmethod
    def age_key(record: FileRecord) -> AgeKey:
        """From the oldest to the newest; the ones with an unknown date (incomplete format) at the end."""
        return (
            record.anio is None,
            record.anio or 0,
            record.mes_num or 0,
            natural_key(record.semana or ""),
            record.destino,
        )

    @staticmethod
    def newness_key(record: FileRecord) -> NewnessKey:
        """Greater = newer: last modification of the original; on a tie, the most recent folder and the path."""
        return (
            record.modificado,
            record.anio or 0,
            record.mes_num or 0,
            natural_key(record.semana or ""),
            record.origen,
        )

    @staticmethod
    def group(records: Iterable[FileRecord]) -> list[DuplicateGroup]:
        """Groups sorted from most to least recoverable space."""
        by_hash: dict[str, list[FileRecord]] = defaultdict(list)
        for record in records:
            if record.sha256 and record.bytes > 0:
                by_hash[record.sha256].append(record)
        groups = []
        for sha, members in by_hash.items():
            if len(members) < 2:
                continue
            members.sort(key=Duplicates.newness_key, reverse=True)
            groups.append(DuplicateGroup(sha, members[0].bytes, members[0], tuple(members[1:])))
        groups.sort(key=lambda g: (g.recoverable, len(g.members)), reverse=True)
        return groups

    @staticmethod
    def summarize(groups: list[DuplicateGroup]) -> DuplicatesSummary:
        return DuplicatesSummary(
            grupos=len(groups),
            copias=sum(len(g.copies) for g in groups),
            recuperable=sum(g.recoverable for g in groups),
        )

    @staticmethod
    def new_in_run(groups: list[DuplicateGroup], origins: Iterable[str]) -> list[NewDuplicate]:
        """Files of a run (by their origin) whose content had already been processed before.

        First go the ones processed in previous runs and then the ones of this run, in processing order: if two
        equal files arrive together, only the second one is reported, pointing to the first.
        """
        in_run = set(origins)
        result = []
        for g in groups:
            order = sorted(g.members, key=lambda r: (r.origen in in_run, r.procesado_en, Duplicates.age_key(r)))
            first = order[0]
            result += [NewDuplicate(r.destino, first.destino) for r in order[1:] if r.origen in in_run]
        return sorted(result, key=lambda d: d.new)
