"""Data adapters: implementations of models.ORMAdapter, models.SQLConverter, models.FileAdapter and, over HTTP to
data, models.RawStore (feature 042).

The only package that imports the ORM (only sqlalchemy_converter.py) and that uses pathlib, shutil, os and stat
(only local_files.py).
"""

from .local_files import LocalFileAdapter, absolute_path, folder_and_name, overlaps, project_path
from .raw_store import HttpRawStore, raw_properties, raw_store
from .sources import open_source, overlaps_ingest
from .sql_adapter import SQLORMAdapter, create_adapter, visible_url
from .sqlalchemy_converter import SqlAlchemyConverter

__all__ = [
    "HttpRawStore",
    "LocalFileAdapter",
    "SQLORMAdapter",
    "SqlAlchemyConverter",
    "absolute_path",
    "create_adapter",
    "folder_and_name",
    "open_source",
    "overlaps",
    "overlaps_ingest",
    "project_path",
    "raw_properties",
    "raw_store",
    "visible_url",
]
