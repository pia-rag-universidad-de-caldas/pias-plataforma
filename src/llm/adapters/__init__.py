"""llm adapters: implementations of the models ports. The only package that uses httpx.

ollama_client.py (and its mappers) is Ollama, the only place that talks to it; data/ is the active configuration over
data; session.py opens it per request.
"""

from .data import GraphConfigStore
from .ollama_client import OllamaClient, missing
from .session import HttpSession

__all__ = ["GraphConfigStore", "HttpSession", "OllamaClient", "missing"]
