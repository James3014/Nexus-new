"""Guard for the 2026-10-17 dead-code retirement (batch B4, Issue #2475).

See ARCHIVED_2026-10-17_deadcode_b4.md. The modules below were physically deleted
after an Owner decision. These tests fail if one comes back (as a module, a package
or a same-named data file), or if code under nexus/ or scripts/ (archive excluded)
starts importing or naming one again, so re-adding is deliberate.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("nexus", "scripts")
SCAN_EXCLUDED_PREFIXES = ("scripts/archive/",)
TEXT_SUFFIXES = {".py", ".json", ".txt", ".toml", ".yaml", ".yml", ".cfg", ".ini", ".sh"}
REAPPEAR_SUFFIXES = (".py", ".json", ".txt")

PACKAGE = "nexus.services"
RETIRED_NAMES = (
    "ambiguity_guard",
    "aos_oracle",
    "arweave_writer",
    "construction_service",
    "context_crystal",
    "dual_phase_d",
    "feature_tasker",
    "fp_bridge_v2",
    "fs_watcher",
    "governance_sink",
    "local_deliberation_lane",
    "mcp_delegator",
    "mock_llm",
    "normalization_engine",
    "planner_enhancer",
    "predictive_audit",
    "rbac",
    "s2t_repair",
    "shannon_audit",
    "shogun_optimizer",
    "steward",
    "swarm_graph",
    "ui_budget",
)
RETIRED_MODULES = tuple(f"{PACKAGE}.{name}" for name in RETIRED_NAMES)
PACKAGE_DIR = PACKAGE.replace(".", "/")


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(REPO_ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imported_modules(path: Path, tree: ast.AST) -> set[str]:
    """Absolute dotted names a module imports (relative imports resolved)."""
    module = _module_name(path)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = package.split(".")
                if node.level > 1:
                    anchor = anchor[: len(anchor) - (node.level - 1)]
                base = ".".join(anchor + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            first = node.args[0]
            if (
                called in {"import_module", "__import__", "find_spec"}
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
            ):
                names.add(first.value)
    return names


def _is_retired(name: str) -> bool:
    return any(name == retired or name.startswith(retired + ".") for retired in RETIRED_MODULES)


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for top in SCAN_ROOTS:
        for path in sorted((REPO_ROOT / top).rglob("*")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if "__pycache__" in path.parts or rel.startswith(SCAN_EXCLUDED_PREFIXES):
                continue
            if path.is_file() and path.suffix in TEXT_SUFFIXES:
                files.append(path)
    return files


def _name_pattern() -> re.Pattern[str]:
    alternatives = []
    for name in RETIRED_NAMES:
        alternatives.append(rf"\b{re.escape(PACKAGE)}\.{name}\b")
        alternatives.append(rf"\b{re.escape(PACKAGE_DIR)}/{name}\b")
    return re.compile("|".join(alternatives))


@pytest.mark.parametrize("name", RETIRED_NAMES)
def test_retired_deadcode_b4_path_absent(name: str) -> None:
    base = REPO_ROOT / PACKAGE_DIR / name
    present = [
        str(p.relative_to(REPO_ROOT))
        for p in (base, *(base.with_suffix(s) for s in REAPPEAR_SUFFIXES))
        if p.exists()
    ]
    assert present == [], f"retired in #2475 but present again: {present}"


@pytest.mark.parametrize("module", RETIRED_MODULES)
def test_retired_deadcode_b4_module_not_importable(module: str) -> None:
    try:
        spec = importlib.util.find_spec(module)
    except ModuleNotFoundError:
        spec = None
    assert spec is None, f"{module} was retired (Issue #2475) but is importable again"


def test_retired_deadcode_b4_not_imported() -> None:
    offenders: list[str] = []
    for path in _scanned_files():
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        except SyntaxError:
            continue  # the text scan below still covers this file
        hits = sorted(name for name in _imported_modules(path, tree) if _is_retired(name))
        offenders.extend(f"{path.relative_to(REPO_ROOT)}: {name}" for name in hits)
    assert offenders == []


def test_retired_deadcode_b4_not_named() -> None:
    pattern = _name_pattern()
    offenders: list[str] = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {match.group(0)}")
    assert offenders == []


def test_retired_deadcode_b4_guard_detects_reference() -> None:
    """The scans are not vacuous: each import or naming form of a retired module is flagged."""
    sample = REPO_ROOT / "nexus" / "services" / "sample.py"
    for source in (
        "import nexus.services.aos_oracle\n",
        "from nexus.services import mcp_delegator\n",
        "from .planner_enhancer import enhance_planner_context\n",
        "from nexus.services.s2t_repair import S2TRepairCandidateLoop\n",
        "importlib.import_module('nexus.services.fs_watcher')\n",
    ):
        names = _imported_modules(sample, ast.parse(source))
        assert any(_is_retired(name) for name in names), source
    assert not any(
        _is_retired(name)
        for name in _imported_modules(sample, ast.parse("from .s2t_strict import x\n"))
    )
    pattern = _name_pattern()
    assert pattern.search('{"module": "nexus.services.governance_sink"}')
    assert pattern.search("see nexus/services/local_deliberation_lane.py")
    assert not pattern.search("nexus.services.s2t_strict and nexus/services/steward_v2")
