"""Chunking adapters: implementations of the models ports. The only package that uses docling and httpx.

One folder per other side of a connection, with its clients, its mappers and the facade that implements the port:
http/ (base client, pages, probe), ingesta/ (IngestaHttpSource), data/ (GraphHttpSink, GraphExperimentStore);
session.py puts them together for a run. docling_converter.py and strategies/ do the chunking itself.
"""

from .data import GraphExperimentStore, GraphHttpSink
from .docling_converter import DoclingConverter
from .http import HttpServiceProbe
from .ingesta import IngestaHttpSource
from .session import HttpSession
from .strategies import Models, SectionStrategies

__all__ = [
    "DoclingConverter",
    "GraphExperimentStore",
    "GraphHttpSink",
    "HttpServiceProbe",
    "HttpSession",
    "IngestaHttpSource",
    "Models",
    "SectionStrategies",
]
