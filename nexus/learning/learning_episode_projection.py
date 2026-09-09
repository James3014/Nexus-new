"""Compatibility facade for canonical Learning episode projection.

Canonical implementation authority lives in ``James3014/nexus-learning``.
This legacy module intentionally contains no fallback implementation.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType

CANONICAL_IMPLEMENTATION_MODULE = "nexus_learning.episode_projection"


def _load_canonical() -> ModuleType:
    try:
        return import_module(CANONICAL_IMPLEMENTATION_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.split(".")[0] == "nexus_learning":
            raise RuntimeError(
                "Canonical Learning episode projection requires the standalone nexus-learning "
                "package under Python >=3.11; the legacy implementation fallback is disabled."
            ) from exc
        raise


_CANONICAL = _load_canonical()
_PUBLIC_NAMES = tuple(sorted(name for name in dir(_CANONICAL) if not name.startswith("_")))
globals().update({name: getattr(_CANONICAL, name) for name in _PUBLIC_NAMES})
__all__ = list(_PUBLIC_NAMES)


def __getattr__(name: str):
    return getattr(_CANONICAL, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_CANONICAL)))
