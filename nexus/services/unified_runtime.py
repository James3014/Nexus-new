"""Compatibility facade for the canonical ``UnifiedRuntime`` package.

The runtime implementation is owned by the installed ``nexus-runtime``
package.  This module preserves the historical import path while forwarding
lookups to that package without retaining a local implementation fallback.
"""

from __future__ import annotations

from .runtime_compat import _RUNTIME


def __getattr__(name: str):
    """Resolve legacy imports from the canonical runtime export surface."""
    try:
        return getattr(_RUNTIME, name)
    except AttributeError as exc:
        raise AttributeError(
            f"nexus runtime export is unavailable: {name}"
        ) from exc


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_RUNTIME.names()))


__all__ = tuple(_RUNTIME.names())
