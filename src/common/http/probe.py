"""Whether a route of the same server answers: a yes or no, outside the base client (the health of the modules)."""

import httpx

from common.config import HTTP_TIMEOUT


def responds(base_url: str, path: str, timeout: float = HTTP_TIMEOUT) -> bool:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}{path}", timeout=timeout)
    except httpx.HTTPError:
        return False
    return response.is_success
