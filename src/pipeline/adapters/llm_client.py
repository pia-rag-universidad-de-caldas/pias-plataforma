"""LlmClient: the contract of feature 048 with the llm module (feature 047; its routes are the constants of
pipeline.config).

GET {llm}/models  → {admitted: [{name, context, vision, installed, default}], installed: [{name, size, family, ...}]}
PUT {llm}/config  {model, temperature?, num_ctx?, max_tokens?, system?} → the active one (422 if it doesn't fit)
"""

import httpx

from pipeline.config import LLM_CONFIG, LLM_MODELS
from pipeline.models import JsonObject, LlmModel, LlmPort, NotFoundError, UnavailableError

from .http import BaseHttpClient, Json, errors


def _installed(body: Json) -> set[str]:
    """The names of the downloaded models (the `installed` list), for an admitted model that doesn't say it."""
    items = body.get("installed") if isinstance(body, dict) else None
    if not isinstance(items, list):
        return set()
    return {str(i.get("name")) for i in items if isinstance(i, dict) and isinstance(i.get("name"), str)}


def _model(raw: Json, installed: set[str]) -> LlmModel:
    if not isinstance(raw, dict):
        raise UnavailableError(f"llm answered a model that isn't an object: {raw!r}")
    name, context = raw.get("name"), raw.get("context")
    if not isinstance(name, str) or not name:
        raise UnavailableError(f"llm answered a model without name: {raw!r}")
    flag = raw.get("installed")
    return LlmModel(
        name=name,
        context=context if isinstance(context, int) and not isinstance(context, bool) else None,
        vision=raw.get("vision") is True,
        installed=flag if isinstance(flag, bool) else name in installed,
        default=raw.get("default") is True,
    )


class LlmClient(BaseHttpClient, LlmPort):
    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, path, errors("llm"))

    def models(self) -> list[LlmModel]:
        found = self._get(LLM_MODELS)
        if found is None:
            raise UnavailableError(f"llm has no {self._path}{LLM_MODELS} route")
        admitted = found.get("admitted") if isinstance(found, dict) else None
        if not isinstance(admitted, list):
            raise UnavailableError(f"llm answered its models without `admitted`: {str(found)[:300]}")
        installed = _installed(found)
        return [_model(m, installed) for m in admitted]

    def apply(self, config: JsonObject) -> None:
        if self._request("PUT", LLM_CONFIG, body=config) is None:
            raise NotFoundError(f"llm has no {self._path}{LLM_CONFIG} route")
