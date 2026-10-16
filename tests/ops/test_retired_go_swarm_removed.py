"""The retired Go swarm trees stay deleted (Owner decision 2026-10-16).

``nexus_swarm/`` and ``nexus-swarm-v22-prod/`` had no live build, deploy or
import path. These tests make a re-add deliberate: bringing either tree back,
or importing ``nexus_swarm`` from ``nexus/`` or ``scripts/``, turns them red.
"""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RETIRED_TREES = ("nexus_swarm", "nexus-swarm-v22-prod")
RETIRED_PACKAGE = "nexus_swarm"
# Source kinds that made up the deleted trees. Ignored local leftovers (sqlite
# files, certificates, built binaries) are not source and are not checked.
SOURCE_SUFFIXES = {".py", ".go", ".proto", ".mod", ".sum", ".yaml", ".yml", ".tpl", ".sh", ".md"}
# Archived, never-registered CLI modules (#1906). Their nexus_swarm imports sit
# inside command bodies, so importing the module still works; the commands fail.
ARCHIVED_LAZY_IMPORTERS = {
    "nexus/cli/commands/guard.py",
    "nexus/cli/commands/healing.py",
    "nexus/cli/commands/swarm.py",
}


def _imports_retired(node: ast.AST) -> bool:
    if isinstance(node, ast.Import):
        return any(alias.name.split(".")[0] == RETIRED_PACKAGE for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        return node.level == 0 and (node.module or "").split(".")[0] == RETIRED_PACKAGE
    if isinstance(node, ast.Call) and node.args:
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        first = node.args[0]
        return (
            name in {"import_module", "__import__"}
            and isinstance(first, ast.Constant)
            and isinstance(first.value, str)
            and first.value.split(".")[0] == RETIRED_PACKAGE
        )
    return False


def _module_level_nodes(tree: ast.Module) -> list[ast.AST]:
    """Every node not nested inside a function body."""
    found: list[ast.AST] = []
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        found.append(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(node))
    return found


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return None


@pytest.mark.parametrize("tree", RETIRED_TREES)
def test_retired_swarm_tree_has_no_source(tree: str) -> None:
    base = ROOT / tree
    leftovers = [
        p.relative_to(ROOT).as_posix()
        for p in (base.rglob("*") if base.exists() else [])
        if p.is_file() and (p.suffix in SOURCE_SUFFIXES or p.name == "Dockerfile")
    ]
    assert leftovers == [], (
        f"{tree} was deleted on 2026-10-16; re-adding it needs an Owner decision"
    )


@pytest.mark.parametrize(
    "module",
    [
        "nexus_swarm.guard.consensus_guard",
        "nexus_swarm.healing.predictive_healer",
        "nexus_swarm.wisdom.online_learner",
    ],
)
def test_retired_swarm_python_modules_are_not_importable(module: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)


def test_no_python_source_imports_the_retired_swarm_package() -> None:
    offenders: list[str] = []
    for top in ("nexus", "scripts"):
        for path in sorted((ROOT / top).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = _parse(path)
            if tree is None:
                continue
            rel = path.relative_to(ROOT).as_posix()
            nodes = _module_level_nodes(tree) if rel in ARCHIVED_LAZY_IMPORTERS else ast.walk(tree)
            if any(_imports_retired(node) for node in nodes):
                offenders.append(rel)
    assert offenders == []


def test_archived_cli_swarm_commands_fail_closed_without_the_package() -> None:
    from click.testing import CliRunner

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        guard = importlib.import_module("nexus.cli.commands.guard")
        healing = importlib.import_module("nexus.cli.commands.healing")
    runner = CliRunner()
    for command, args in (
        (guard.guard_group, ["validate", "--file", "x.py"]),
        (healing.healing_group, ["forecast"]),
    ):
        result = runner.invoke(command, args)
        assert result.exit_code != 0
        assert isinstance(result.exception, ModuleNotFoundError)
