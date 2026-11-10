"""Check: which documents have to be parsed (what a run skips, and POST /runs without sha256s), without writing."""

from collections.abc import Iterable, Sequence

from parsing.models import ParseStatus, RawState


class Check:
    @staticmethod
    def done(state: RawState, fingerprint: str) -> bool:
        """Parsed whole with this fingerprint: nothing to do. A partial or failed one, or one of another fingerprint,
        is pending."""
        return state.status is ParseStatus.PARSED and state.fingerprint == fingerprint

    @staticmethod
    def unique(sha256s: Sequence[str]) -> list[str]:
        """In order, repeated ones once."""
        return list(dict.fromkeys(sha256s))

    @staticmethod
    def pending(states: Iterable[RawState], fingerprint: str, redo: bool = False) -> list[RawState]:
        """The current RAW (vigente) that have to be parsed, by sha256; with `redo`, every current one."""
        found = (s for s in states if s.vigente and (redo or not Check.done(s, fingerprint)))
        return sorted(found, key=lambda s: s.sha256)
