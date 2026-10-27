"""ServiceProbe over HTTP (httpx) against the same server. The only HTTP client of chunking (Ruff TID251)."""

import httpx

from chunking.config import HTTP_TIMEOUT
from chunking.models import ServiceProbe


class HttpServiceProbe(ServiceProbe):
    def __init__(self, base_url: str, timeout: float = HTTP_TIMEOUT) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def responds(self, path: str) -> bool:
        try:
            response = httpx.get(f"{self._base_url}{path}", timeout=self._timeout)
        except httpx.HTTPError:
            return False
        return response.is_success
