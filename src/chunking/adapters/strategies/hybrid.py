"""Strategy `hybrid`: consecutive elements under the same headings joined while they fit max_tokens (merge_peers);
an element over it is split in windows. Without merge_peers, one chunk per element (split if too long)."""

from chunking.models import ChunkPiece, DocumentSection, StrategyParameters

from .base import Unit, fit, units
from .tools import Models


def hybrid(section: DocumentSection, parameters: StrategyParameters, models: Models) -> list[ChunkPiece]:
    assert parameters.max_tokens is not None
    tokens, limit = models.tokens(parameters.tokenizer), parameters.max_tokens
    groups: list[list[Unit]] = []
    for unit in units(section):
        last = groups[-1] if groups else None
        joined = "\n".join([*(u.text for u in last), unit.text]) if last else ""
        if parameters.merge_peers and last and last[0].headings == unit.headings and tokens.count(joined) <= limit:
            last.append(unit)
        else:
            groups.append([unit])
    return [piece for group in groups for piece in fit(group, tokens, limit)]
