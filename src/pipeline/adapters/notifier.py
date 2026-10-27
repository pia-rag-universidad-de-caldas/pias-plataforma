"""HttpNotifier: tells an actor (POST to its callback_url) that a stage is waiting for it. No retries: if it fails,
the stage is still in the inbox."""

import httpx

from pipeline.config import HTTP_TIMEOUT
from pipeline.models import Actor, JsonObject, Notifier


class HttpNotifier(Notifier):
    def __init__(self, timeout: float = HTTP_TIMEOUT) -> None:
        self._timeout = timeout

    def notify(self, actor: Actor, payload: JsonObject) -> str | None:
        if not actor.callback_url:
            return None
        try:
            response = httpx.post(actor.callback_url, json=payload, timeout=self._timeout)
        except httpx.HTTPError as e:
            return f"{actor.callback_url}: {e}"
        return None if response.is_success else f"{actor.callback_url}: {response.status_code}"
