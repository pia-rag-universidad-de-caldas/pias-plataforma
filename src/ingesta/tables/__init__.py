"""Project tables, described without SQL or ORM syntax. The adapter's `from_scratch` constructor creates them;
`from_existing` opens them and migrates the old ones (`needs_migration` rule of each TableSpec)."""

from .categories_table import CATEGORIES, FILE_CATEGORIES
from .files_table import FILES
from .ingestions_table import INGESTIONS
from .runs_table import RUNS
from .uploads_table import UPLOADS

# In dependency order: the referenced ones (archivos, categorias) before the relationship.
TABLES = (FILES, RUNS, CATEGORIES, FILE_CATEGORIES, INGESTIONS, UPLOADS)

__all__ = ["CATEGORIES", "FILES", "FILE_CATEGORIES", "INGESTIONS", "RUNS", "TABLES", "UPLOADS"]
