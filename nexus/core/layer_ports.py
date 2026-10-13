"""Core-owned ports for upper-layer collaborators (#1923).

``nexus.core`` must not depend on ``nexus.engine`` or ``nexus.app``. Core
code that needs one of their collaborators (an executor class, a receipt
projector, the planner) asks for it by *port name* through
:func:`resolve_port`. The owning layer binds its implementations onto these
ports (``nexus.engine.core_ports`` / ``nexus.app.core_ports``) and the
package composition root (``nexus/__init__.py``) performs that binding once,
before any ``nexus.core`` module can run.

Core holds no module paths of the upper layers. An unbound port fails
closed with :class:`PortUnbound`; there is no fallback and no substitute.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable, Mapping

PortLoader = Callable[[], Any]

_LOADERS: dict[str, PortLoader] = {}


class PortUnbound(LookupError):
    """Raised when core asks for a port nothing has bound."""


def register_port(name: str, loader: PortLoader) -> None:
    """Bind ``name`` to a zero-argument loader returning the collaborator."""
    if not name:
        raise ValueError("port name must be non-empty")
    _LOADERS[name] = loader


def bind_lazy_ports(table: Mapping[str, tuple[str, str]]) -> None:
    """Bind ``{port: (module, attribute)}`` supplied by the owning layer.

    The module is imported when the port is resolved, not when it is bound,
    matching the in-function imports these ports replace. An empty
    attribute binds the module itself.
    """
    for name, (module_path, attribute) in table.items():
        register_port(name, _lazy_loader(module_path, attribute))


def _lazy_loader(module_path: str, attribute: str) -> PortLoader:
    def load() -> Any:
        module = importlib.import_module(module_path)
        return getattr(module, attribute) if attribute else module

    return load


def resolve_port(name: str) -> Any:
    """Return the collaborator bound to ``name``; the loader runs at call time."""
    loader = _LOADERS.get(name)
    if loader is None:
        raise PortUnbound(f"PORT_UNBOUND:{name}")
    return loader()


def registered_ports() -> frozenset[str]:
    return frozenset(_LOADERS)
