"""Issue #2260 item 1: the dispatcher boundary uses only public cli_worker names."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BOUNDARY = ROOT / "nexus" / "executors" / "agy_dispatch_boundary.py"


def _cli_worker_aliases(tree: ast.AST) -> set[str]:
    """Local names bound to the ``nexus.executors.cli_worker`` module."""
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "nexus.executors":
            aliases |= {a.asname or a.name for a in node.names if a.name == "cli_worker"}
        elif isinstance(node, ast.Import):
            aliases |= {
                a.asname for a in node.names if a.name == "nexus.executors.cli_worker" and a.asname
            }
    return aliases


def private_cli_worker_references(source: str) -> list[str]:
    tree = ast.parse(source)
    aliases = _cli_worker_aliases(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr.startswith("_")
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            found.append(f"line {node.lineno}: cli_worker.{node.attr}")
        elif isinstance(node, ast.ImportFrom) and node.module == "nexus.executors.cli_worker":
            found += [
                f"line {node.lineno}: from cli_worker import {a.name}"
                for a in node.names
                if a.name.startswith("_")
            ]
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") in {"getattr", "hasattr"}:
            args = node.args
            if (
                len(args) >= 2
                and isinstance(args[0], ast.Name)
                and args[0].id in aliases
                and isinstance(args[1], ast.Constant)
                and str(args[1].value).startswith("_")
            ):
                found.append(f"line {node.lineno}: getattr cli_worker.{args[1].value}")
    return found


def test_agy_dispatch_boundary_references_no_private_cli_worker_name() -> None:
    assert "cli_worker" in _cli_worker_aliases(ast.parse(BOUNDARY.read_text(encoding="utf-8")))
    assert private_cli_worker_references(BOUNDARY.read_text(encoding="utf-8")) == []


def test_private_reference_scanner_detects_each_access_form() -> None:
    source = (
        "from nexus.executors import cli_worker as cw\n"
        "from nexus.executors.cli_worker import _sweep_baseline\n"
        "cw._RUN_START_TICKS\n"
        "getattr(cw, '_DescendantTracker')\n"
        "cw.public_name\n"
    )
    found = private_cli_worker_references(source)
    assert len(found) == 3, found
