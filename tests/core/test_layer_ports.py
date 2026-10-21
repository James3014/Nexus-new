"""#1923: nexus.core reaches engine/app collaborators only through core-owned ports."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

import nexus  # noqa: F401  # composition root binds the ports
from nexus.app.core_ports import CORE_APP_PORTS
from nexus.core import capability_executor_registry as registry
from nexus.core import layer_ports
from nexus.engine.core_ports import CORE_ENGINE_PORTS

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_DIR = REPO_ROOT / "nexus" / "core"
CORE_FILES = sorted(CORE_DIR.rglob("*.py"))
# Deleted 2026-10-21 (#2584 Phase-2 batch B, ARCHIVED_2026-10-21_phase2_batch_B.md). Kept
# as explicit parameters so their test ids stay stable; each case asserts the file is gone.
RETIRED_CORE_FILES = (CORE_DIR / "planner_auditor.py",)
_UPPER_LAYER_NAMES = frozenset({"engine", "app"})
_UPPER_LAYER_TEXT = re.compile(r"nexus\.(?:engine|app)\b")
# Receipt metadata naming the physical implementation is identity, not a dependency.
_METADATA_KEYS = frozenset({"physical_callable"})
_PORT_USE = re.compile(r'(?:resolve_port|_try_port|_port_error)\("([^"]+)"\)')


def _constant_text(node: ast.AST) -> str | None:
    """Constant text of a str literal, f-string, or ``+`` concatenation; None otherwise."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                parts.append(_constant_text(value.value) or "")
            else:
                parts.append(_constant_text(value) or "")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _constant_text(node.left), _constant_text(node.right)
        if left is None and right is None:
            return None
        return (left or "") + (right or "")
    return None


def _is_string_expr(node: ast.AST) -> bool:
    return _constant_text(node) is not None


def _upper_layer_references(source: str) -> list[str]:
    """Every way a core module could load nexus.engine / nexus.app."""
    tree = ast.parse(source)
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    hits: list[str] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            hits.extend(
                f"{line}:import {a.name}" for a in node.names if _UPPER_LAYER_TEXT.match(a.name)
            )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = {a.name for a in node.names}
            absolute_hit = node.level == 0 and (
                _UPPER_LAYER_TEXT.match(module)
                or (module == "nexus" and names & _UPPER_LAYER_NAMES)
            )
            # nexus/core/x.py: ``from ..engine import y`` / ``from .. import engine``
            relative_hit = node.level >= 2 and (
                module.split(".")[0] in _UPPER_LAYER_NAMES
                or (not module and names & _UPPER_LAYER_NAMES)
            )
            if absolute_hit or relative_hit:
                hits.append(f"{line}:from {'.' * node.level}{module} import {sorted(names)}")
        elif _is_string_expr(node):
            parent = parents.get(node)
            if parent is not None and _is_string_expr(parent):
                continue  # judged as part of the enclosing concatenation / f-string
            text = _constant_text(node) or ""
            if not _UPPER_LAYER_TEXT.search(text):
                continue
            if isinstance(parent, ast.Expr):
                continue  # docstring / bare string statement
            if isinstance(parent, ast.keyword) and parent.arg in _METADATA_KEYS:
                continue
            if isinstance(parent, ast.Dict):
                key = parent.keys[parent.values.index(node)] if node in parent.values else None
                if isinstance(key, ast.Constant) and key.value in _METADATA_KEYS:
                    continue
            hits.append(f"{line}:string {text!r}")
    return hits


@pytest.mark.parametrize(
    "path",
    sorted({*CORE_FILES, *RETIRED_CORE_FILES}),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_core_modules_do_not_load_upper_layer_modules(path: Path) -> None:
    if path in RETIRED_CORE_FILES:
        assert not path.exists(), f"{path.relative_to(REPO_ROOT)} was retired (#2584)"
        return
    assert _upper_layer_references(path.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    "source",
    [
        "from nexus.engine.x import y",
        "import nexus.app.x",
        "from nexus import engine",
        "from .. import app",
        "from ..engine.x import y",
        'importlib.import_module("nexus.engine.x")',
        'importlib.import_module(name="nexus.engine.x")',
        '_try_import_class(module_path="nexus.app.x", class_name="Y")',
        'importlib.import_module("nexus." + "engine.x")',
        'importlib.import_module(f"nexus.{layer}engine.x")',
        "importlib.import_module(f\"nexus.{'engine'}.x\")",
        'MODULE = "nexus.engine.x"',
    ],
)
def test_scanner_rejects_import_dodges(source: str) -> None:
    assert _upper_layer_references(source), source


def test_scanner_allows_receipt_metadata() -> None:
    source = (
        'f(physical_callable="nexus.engine.x.Y.run")\n'
        'g({"physical_callable": "nexus.app.x." + "Y.run"})\n'
        '"""Docstring naming nexus.engine is prose."""\n'
    )
    assert _upper_layer_references(source) == []


def test_every_port_used_by_core_is_bound() -> None:
    used: set[str] = set()
    for path in CORE_FILES:
        used |= set(_PORT_USE.findall(path.read_text(encoding="utf-8")))
    assert used
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


def test_try_port_miss_names_port_in_receipt_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(layer_ports._LOADERS, "ddtree.DDTreeAdapter")
    assert registry._try_port("ddtree.DDTreeAdapter") is None
    assert registry._port_error("ddtree.DDTreeAdapter") == "PORT_UNBOUND:ddtree.DDTreeAdapter"

    def broken() -> object:
        raise ImportError("boom")

    monkeypatch.setitem(layer_ports._LOADERS, "ddtree.DDTreeAdapter", broken)
    assert registry._try_port("ddtree.DDTreeAdapter") is None
    assert registry._port_error("ddtree.DDTreeAdapter") == "PORT_LOAD_FAILED:ddtree.DDTreeAdapter"


def test_import_time_port_resolves_in_fresh_interpreter() -> None:
    """learning_steward resolves its port at import; the composition root must bind first."""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import nexus.core.learning_steward as m; print(m.MIN_EVOLUTION_STEPS)",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "10"
