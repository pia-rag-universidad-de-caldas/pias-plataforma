"""Composition root (feature 020): one HTTP server with each module under its prefix (/ingesta, /data,
/chunking, /pipeline).

The only package that imports ingesta, data, chunking and pipeline; the modules don't import each other (Ruff TID251 in
each module's ruff.toml) and talk to each other over HTTP against this same server (ServerSettings.self_url).
"""

from .app import create_app
from .graph import UnavailableGraph, open_graph
from .server import serve
from .settings import ServerSettings

__all__ = ["ServerSettings", "UnavailableGraph", "create_app", "open_graph", "serve"]
