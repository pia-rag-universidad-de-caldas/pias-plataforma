"""Strategy `page`: one chunk per page of the section (split if it goes over max_tokens). An element that crosses a
page break counts in the page where it starts, so every chunk has one page. Without pages (a .docx), the whole
section, like `section`."""

from chunking.models import ChunkPiece, DocumentSection, StrategyParameters

from .base import Unit, fit, units
from .tools import Models


def page(section: DocumentSection, parameters: StrategyParameters, models: Models) -> list[ChunkPiece]:
    assert parameters.max_tokens is not None
    tokens, limit = models.tokens(parameters.tokenizer), parameters.max_tokens
    groups: list[tuple[int | None, list[Unit]]] = []
    for unit in units(section):
        number = unit.pages[0] if unit.pages else (groups[-1][0] if groups else None)
        if groups and groups[-1][0] == number:
            groups[-1][1].append(unit)
        else:
            groups.append((number, [unit]))
    return [piece for number, group in groups for piece in fit(group, tokens, limit, page=number)]
