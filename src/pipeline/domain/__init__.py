"""Pipeline rules, without I/O: the catalog of actions, the order of stages, the run's state machine."""

from . import experiments, order
from .actions import CATALOG, PARSED_SELECT, REVIEW_SCORE, SELECT, action, kind
from .engine import EXTERNAL, Engine, Step
from .merge import deep_merge
from .pairing import Pair, check_cycles, fit, fit_llm, lab_cycles, pair
from .scope import scoped
from .templates import BUILTIN, EXPERIMENTS, LABORATORY, PRODUCTION

__all__ = [
    "BUILTIN",
    "CATALOG",
    "EXPERIMENTS",
    "EXTERNAL",
    "LABORATORY",
    "PARSED_SELECT",
    "PRODUCTION",
    "REVIEW_SCORE",
    "SELECT",
    "Engine",
    "Pair",
    "Step",
    "action",
    "check_cycles",
    "deep_merge",
    "experiments",
    "fit",
    "fit_llm",
    "kind",
    "lab_cycles",
    "order",
    "pair",
    "scoped",
]
