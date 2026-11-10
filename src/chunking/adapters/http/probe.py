"""ServiceProbe over HTTP against the same server."""

from chunking.models import ServiceProbe
from common.http import responds


class HttpServiceProbe(ServiceProbe):
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def responds(self, path: str) -> bool:
        return responds(self._base_url, path)
