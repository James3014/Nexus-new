"""Manifest-listed host runtime scripts must ship every sibling file they load.

Bug family: ``nexus-dsh-workflow`` loads ``exact_base_tool_gate.py`` from its own
directory at runtime, but the installed host snapshot lacked it (Refs #2537).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "scripts" / "ops" / "nexus-host-runtime-manifest.json"
SCAN_SUFFIXES = ("", ".py")


def _manifest_paths() -> set[str]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {entry["path"] for entry in data["runtime_files"]}


def _is_file_ref(node: ast.AST) -> bool:
    """True for ``__file__``, ``Path(__file__)`` and chains of ``.resolve()``."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == "__file__":
            return True
    return False


def _sibling_targets(tree: ast.AST) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(tree):
        # Path(__file__).resolve().with_name("x")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "with_name"
            and _is_file_ref(node.func.value)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            targets.add(node.args[0].value)
        # Path(__file__).resolve().parent / "x"
        if (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Div)
            and isinstance(node.left, ast.Attribute)
            and node.left.attr == "parent"
            and _is_file_ref(node.left.value)
            and isinstance(node.right, ast.Constant)
            and isinstance(node.right.value, str)
        ):
            targets.add(node.right.value)
    return targets


def _scan(path: Path) -> set[str]:
    return _sibling_targets(ast.parse(path.read_text(encoding="utf-8")))


def _scripts() -> list[str]:
    result = []
    for rel in sorted(_manifest_paths()):
        p = ROOT / rel
        if p.suffix in (".json", ".js", ".sh") or not p.is_file():
            continue
        head = p.read_text(encoding="utf-8").splitlines()[:1]
        if p.suffix == ".py" or (head and "python" in head[0]):
            result.append(rel)
    return result


def test_sibling_scanner_detects_known_patterns() -> None:
    tree = ast.parse(
        "from pathlib import Path\n"
        'a = Path(__file__).resolve().parent / "one.py"\n'
        'b = Path(__file__).resolve().with_name("two")\n'
        'c = Path(__file__).with_name("three")\n'
        'd = Path("x").parent / "not-a-sibling"\n'
    )
    assert _sibling_targets(tree) == {"one.py", "two", "three"}


def test_manifest_scripts_ship_every_sibling_they_load() -> None:
    manifest = _manifest_paths()
    scripts = _scripts()
    assert "scripts/ops/nexus-dsh-workflow" in scripts
    missing: list[str] = []
    for rel in scripts:
        directory = Path(rel).parent
        for name in sorted(_scan(ROOT / rel)):
            if f"{directory.as_posix()}/{name}" not in manifest:
                missing.append(f"{rel} loads sibling {name}")
    assert not missing, missing


def test_manifest_scripts_load_tool_gate_from_snapshot() -> None:
    assert "scripts/ops/exact_base_tool_gate.py" in _manifest_paths()
