"""The active configuration (feature 043): GET/PUT/PATCH/DELETE /config. What POST /runs chunks with: the one
someone set (by hand, or with POST /experiments/{id}/apply) or, if nobody did, CHUNKING_DEFAULT. Changing it chunks
nothing: what is done stays as it is until the next POST /runs."""

from dataclasses import asdict, dataclass
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import JsonValue

from chunking.api.dependencies import Config, DocumentChunker, Store
from chunking.api.experiments.responses import DOWN, INVALID
from chunking.api.schemas import ChunkingBody
from chunking.config import CHUNKING_DEFAULT, CHUNKING_FIXED, CHUNKING_VERSION
from chunking.domain import InvalidParameters, Parameters
from chunking.models import ActiveConfig, ConfigOrigin, ConfigValue, NoConfiguration, RequestedChunking
from common.clock import now

router = APIRouter(prefix="/config", tags=["config"])


@dataclass(frozen=True)
class DocumentCounts:
    """The official documents: chunked with the active configuration, with another one, or not chunked."""

    with_active: int
    with_other: int
    not_chunked: int


@dataclass(frozen=True)
class ConfigView:
    chunking: dict[str, ConfigValue] | None  # resolved; None if it can't be used (see `problem`)
    fingerprint: (
        str | None
    )  # of the resolved configuration: GET /data/progress/chunking?fingerprint= says what is missing
    origin: ConfigOrigin
    experiment: str | None
    modified: str | None
    problem: str | None  # why there is no configuration to chunk with (POST /runs answers 409)
    chunking_version: int
    default: dict[str, JsonValue]
    fixed: dict[str, JsonValue]
    documents: DocumentCounts | None = None  # with ?documents=true


def config_view(config: ActiveConfig, docling_version: str, documents: DocumentCounts | None = None) -> ConfigView:
    try:
        parameters, used = Parameters.active(
            config if config.origin is not ConfigOrigin.DEFAULT else None, docling_version
        )
        chunking: dict[str, ConfigValue] | None = parameters.configurable()
        fingerprint: str | None = parameters.fingerprint
        problem = None if used == config else "the stored configuration can't be used: the default applies"
    except NoConfiguration as error:
        chunking, fingerprint, problem, used = None, None, str(error), config
    return ConfigView(
        chunking=chunking,
        fingerprint=fingerprint,
        origin=used.origin,
        experiment=used.experiment,
        modified=used.modified,
        problem=problem,
        chunking_version=CHUNKING_VERSION,
        default=dict(asdict(CHUNKING_DEFAULT)),
        fixed=dict(asdict(CHUNKING_FIXED)),
        documents=documents,
    )


def _check(requested: RequestedChunking, docling_version: str) -> None:
    try:
        Parameters.resolve(requested, docling_version)
    except InvalidParameters as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


def _set(config: Config, requested: RequestedChunking, docling_version: str) -> ConfigView:
    _check(requested, docling_version)
    active = ActiveConfig(requested, ConfigOrigin.MANUAL, None, now())
    config.put(active)
    return config_view(active, docling_version)


@router.get("", responses=DOWN)
def read_config(
    config: Config,
    store: Store,
    chunker: DocumentChunker,
    documents: Annotated[
        bool, Query(description="also count the official documents chunked with it (reads every JSON: slow)")
    ] = False,
) -> ConfigView:
    """The active configuration, where it came from, and what is fixed."""
    version = chunker.version() or ""
    active = config.stored() or Parameters.default()
    counts = None
    if documents:
        try:
            current = Parameters.active(config.stored(), version)[0]
        except NoConfiguration:
            current = None
        found = store.chunked_with()
        counts = DocumentCounts(
            with_active=sum(1 for p in found if p is not None and p == current),
            with_other=sum(1 for p in found if p is not None and p != current),
            not_chunked=sum(1 for p in found if p is None),
        )
    return config_view(active, version, counts)


@router.put("", responses=DOWN | INVALID)
def replace_config(config: Config, chunker: DocumentChunker, body: ChunkingBody) -> ConfigView:
    """Sets the active configuration by hand: what is left out takes the default."""
    return _set(config, body.requested(), chunker.version() or "")


@router.patch("", responses=DOWN | INVALID)
def change_config(config: Config, chunker: DocumentChunker, body: ChunkingBody) -> ConfigView:
    """Changes only what comes; the rest stays as the active configuration has it. Changing the chunker away from
    hybrid drops max_tokens, merge_peers and fit. `fit` (feature 062) replaces tokenizer and max_tokens, and either of
    them replaces fit."""
    current = (config.stored() or Parameters.default()).requested
    chunker_asked = body.chunker or current.chunker
    sized = (chunker_asked or CHUNKING_DEFAULT.chunker) == "hybrid"
    if body.fit is not None:
        tokenizer, max_tokens, fit = body.tokenizer, body.max_tokens, body.budgets()
    elif body.tokenizer is not None or body.max_tokens is not None or not current.fit:
        tokenizer = body.tokenizer or (None if current.fit else current.tokenizer)
        sized_tokens = body.max_tokens if body.max_tokens is not None else current.max_tokens
        max_tokens, fit = (sized_tokens if sized else body.max_tokens), None
    else:  # it keeps the fit it had (only while it stays hybrid)
        tokenizer, max_tokens, fit = None, None, current.fit if sized else None
    requested = RequestedChunking(
        chunker_asked,
        tokenizer,
        max_tokens,
        (body.merge_peers if body.merge_peers is not None else current.merge_peers) if sized else body.merge_peers,
        fit,
    )
    return _set(config, requested, chunker.version() or "")


@router.delete("", responses=DOWN)
def reset_config(config: Config, chunker: DocumentChunker) -> ConfigView:
    """Back to the default (CHUNKING_DEFAULT)."""
    config.clear()
    return config_view(Parameters.default(), chunker.version() or "")
