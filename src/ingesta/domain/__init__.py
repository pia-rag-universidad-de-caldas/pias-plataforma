"""Business rules and processes of the project: one static class per module."""

from .classification import ClassificationMap, Classifier
from .discovery import Discovery
from .duplicates import Duplicates
from .ingestion import Ingestion, IngestionObserver, Stage
from .naming import Naming
from .organization import Organization
from .queries import Queries
from .raw_sync import RawSync
from .repetitions import Repetitions
from .statistics import Statistics
from .uploads import Uploads

__all__ = [
    "ClassificationMap",
    "Classifier",
    "Discovery",
    "Duplicates",
    "Ingestion",
    "IngestionObserver",
    "Naming",
    "Organization",
    "Queries",
    "RawSync",
    "Repetitions",
    "Stage",
    "Statistics",
    "Uploads",
]
