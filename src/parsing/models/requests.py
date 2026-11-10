"""What is asked for."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsingRequest:
    sha256s: list[str] = field(default_factory=list)  # exactly these; repeated ones once
    redo: bool = False  # parse again even those already parsed with the same fingerprint
    simulate: bool = False  # only say what would be parsed
