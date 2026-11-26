"""Rules of consultas, without I/O; everything is imported from consultas.domain."""

from .active_config import checked, config_problems, default_config, resolve, usable
from .asker import Asker, Found
from .attachments import budgets, check, kind, merged, piece_length, pieces, spread, vision_model
from .comparer import Comparer
from .comparisons import Asked, compared_question, comparison_batch, panel_properties
from .prompt import context, fill, messages, with_attachments
from .records import question_batch, title
from .targets import targets

__all__ = [
    "Asked",
    "Asker",
    "Comparer",
    "Found",
    "budgets",
    "check",
    "checked",
    "compared_question",
    "comparison_batch",
    "config_problems",
    "context",
    "default_config",
    "fill",
    "kind",
    "merged",
    "messages",
    "panel_properties",
    "piece_length",
    "pieces",
    "question_batch",
    "resolve",
    "spread",
    "targets",
    "title",
    "usable",
    "vision_model",
    "with_attachments",
]
