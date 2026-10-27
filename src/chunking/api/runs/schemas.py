"""Body of POST /runs (feature 023): a production run and its chunking parameters."""

from dataclasses import dataclass, field
from typing import Annotated

from pydantic import Field

from chunking.api.schemas import Sha256
from chunking.config import (
    MAX_TOKENS,
    MAX_TOKENS_RANGE,
    MERGE_PEERS,
    REPEAT_TABLE_HEADER,
    TABLE_MODE,
    TABLE_STRUCTURE,
    TOKENIZER,
)
from chunking.models import TableMode

DEFAULT_TABLE_MODE = TableMode(TABLE_MODE)


@dataclass(frozen=True)
class RunParameters:
    """The chunking parameters of a production run (`parameters` of POST /runs, feature 023); each missing one takes
    its config default. All of them enter the fingerprint: documents chunked with other values are pending again."""

    tokenizer: str = TOKENIZER  # one of config TOKENIZERS
    max_tokens: Annotated[int, Field(ge=MAX_TOKENS_RANGE[0], le=MAX_TOKENS_RANGE[1])] = MAX_TOKENS
    merge_peers: bool = MERGE_PEERS
    repeat_table_header: bool = REPEAT_TABLE_HEADER  # true may give chunks over max_tokens: those documents fail
    table_structure: bool = TABLE_STRUCTURE
    table_mode: TableMode = DEFAULT_TABLE_MODE


@dataclass(frozen=True)
class NewRun:
    """Body of POST /runs. With `sha256s`, exactly those documents (the filters are ignored) even if already chunked
    with the same parameters; otherwise the chunkable files that match the filters (those of GET /ingesta/data) and
    are pending (new, another content, other parameters, or in error with `retry_errors`)."""

    simulate: bool = False  # only count what would be processed
    types: list[str] = field(default_factory=list)
    year: int | None = None
    month: Annotated[int | None, Field(ge=1, le=12)] = None
    week: str | None = None  # as the folder: Semana_04
    code: str | None = None
    limit: Annotated[int | None, Field(ge=1)] = None  # at most this many documents processed
    retry_errors: bool = False  # retry the documents in error with the same parameters
    sha256s: list[Sha256] = field(default_factory=list)  # as `sha256` in GET /ingesta/data; repeated ones once
    parameters: RunParameters = field(default_factory=RunParameters)
