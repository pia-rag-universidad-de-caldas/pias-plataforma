"""Rules of consultas, without I/O; everything is imported from consultas.domain."""

from .active_config import checked, config_problems, default_config, resolve, usable
from .asker import Asker, Found
from .attachments import budgets, check, kind, merged, piece_length, pieces, spread, vision_model
from .prompt import context, fill, messages, with_attachments
from .records import question_batch, title

__all__ = [
    "Asker",
    "Found",
    "budgets",
    "check",
    "checked",
    "config_problems",
    "context",
    "default_config",
    "fill",
    "kind",
    "merged",
    "messages",
    "piece_length",
    "pieces",
    "question_batch",
    "resolve",
    "spread",
    "title",
    "usable",
    "vision_model",
    "with_attachments",
]
