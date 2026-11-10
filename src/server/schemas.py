"""Response bodies of the root app (the modules keep their own)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleStatus:
    status: str  # "ok" or "unavailable"
    detail: str | None = None  # why it is unavailable


@dataclass(frozen=True)
class ServerHealth:
    status: str  # "ok" if every module is ok; "degraded" otherwise
    version: str
    modules: dict[str, ModuleStatus]  # prefix without "/" → status
