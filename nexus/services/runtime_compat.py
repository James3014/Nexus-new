"""Compatibility forwarding surface for the independently installed runtime.

The runtime package is the sole implementation owner for these execution
symbols.  Resolution is intentionally eager so a missing dependency fails at
startup instead of silently selecting the legacy implementation.
"""

from __future__ import annotations

from nexus_runtime import build_runtime_exports


_RUNTIME = build_runtime_exports()


def __getattr__(name: str):
    try:
        return getattr(_RUNTIME, name)
    except AttributeError as exc:
        raise AttributeError(f"runtime compatibility symbol unavailable: {name}") from exc


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_RUNTIME.names()))


__all__ = ["build_runtime_exports", *_RUNTIME.names()]
