"""#1923: nexus.core reaches engine/app collaborators only through core-owned ports."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import nexus  # noqa: F401  # composition root binds the ports
from nexus.app.core_ports import CORE_APP_PORTS
from nexus.core import layer_ports
from nexus.engine.core_ports import CORE_ENGINE_PORTS

REPO_ROOT = Path(__file__).resolve().parents[2]
_UPPER_LAYERS = ("nexus.engine", "nexus.app")
PORT_CONSUMERS = (
    "nexus/core/capability_executor_registry.py",
    "nexus/core/capability_selector.py",
    "nexus/core/router.py",
)


def _upper_layer_module_references(source: str) -> list[str]:
    """Imports of nexus.engine/nexus.app, including importlib/dotted-string dodges."""
    hits: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(_UPPER_LAYERS):
            hits.append(f"from {node.module}")
        elif isinstance(node, ast.Import):
            hits.extend(a.name for a in node.names if a.name.startswith(_UPPER_LAYERS))
        elif isinstance(node, ast.Call) and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                if first.value.startswith(_UPPER_LAYERS):
                    hits.append(f"call({first.value})")
    return hits


@pytest.mark.parametrize("relpath", PORT_CONSUMERS)
def test_port_consumers_do_not_load_upper_layer_modules(relpath: str) -> None:
    source = (REPO_ROOT / relpath).read_text(encoding="utf-8")
    assert _upper_layer_module_references(source) == []


@pytest.mark.parametrize("relpath", PORT_CONSUMERS)
def test_every_port_used_by_core_is_bound(relpath: str) -> None:
    source = (REPO_ROOT / relpath).read_text(encoding="utf-8")
    used = set(re.findall(r'(?:resolve_port|_try_port)\("([^"]+)"\)', source))
    assert used, relpath
    assert used <= layer_ports.registered_ports()
    for name in used:
        assert layer_ports.resolve_port(name) is not None


def test_bound_ports_resolve_to_owning_layer_objects() -> None:
    assert set(CORE_ENGINE_PORTS) | set(CORE_APP_PORTS) <= layer_ports.registered_ports()
    planner = layer_ports.resolve_port("planner.CapabilityPlanner")
    assert planner.__name__ == "CapabilityPlanner"
    nightshift = layer_ports.resolve_port("nightshift.AutoResearchNightShift")
    assert nightshift.__module__ == "nexus.app.nightshift_runner_service"


def test_unbound_port_fails_closed() -> None:
    with pytest.raises(layer_ports.PortUnbound, match="PORT_UNBOUND:nope.Missing"):
        layer_ports.resolve_port("nope.Missing")
