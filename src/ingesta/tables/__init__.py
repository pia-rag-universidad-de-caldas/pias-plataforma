"""Project tables, described without SQL or ORM syntax. The adapter's `from_scratch` constructor creates them;
`from_existing` opens them and migrates the old ones (`needs_migration` rule of each TableSpec)."""

from .categories_table import CATEGORIES, FILE_CATEGORIES
from .files_table import FILES
from .runs_table import RUNS

# In dependency order: the referenced ones (archivos, categorias) before the relationship.
TABLES = (FILES, RUNS, CATEGORIES, FILE_CATEGORIES)

__all__ = ["CATEGORIES", "FILES", "FILE_CATEGORIES", "RUNS", "TABLES"]
