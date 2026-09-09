"""Compatibility facade for runtime-owned task-context continuity contracts."""

from __future__ import annotations

from nexus_runtime.task_context import continuity as _continuity

__all__ = tuple(
    getattr(
        _continuity,
        "__all__",
        (name for name in dir(_continuity) if not name.startswith("_")),
    )
)


def __getattr__(name: str):
    try:
        return getattr(_continuity, name)
    except AttributeError as exc:
        raise AttributeError(f"runtime task-context export is unavailable: {name}") from exc


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
