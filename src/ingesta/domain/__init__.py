"""Business rules and processes of the project: one static class per module."""

from .classification import ClassificationMap, Classifier
from .discovery import Discovery
from .duplicates import Duplicates
from .ingestion import Ingestion
from .naming import Naming
from .organization import Organization
from .queries import Queries
from .repetitions import Repetitions
from .statistics import Statistics

__all__ = [
    "ClassificationMap",
    "Classifier",
    "Discovery",
    "Duplicates",
    "Ingestion",
    "Naming",
    "Organization",
    "Queries",
    "Repetitions",
    "Statistics",
]
