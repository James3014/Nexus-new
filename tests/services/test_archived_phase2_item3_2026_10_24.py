"""Guard for the 2026-10-24 Phase-2 retirement of item 3 (Issue #2584).

See ARCHIVED_2026-10-24_phase2_item3.md. Deleted on the Owner's decision of 2026-10-24
("delete as recommended") under the standing Phase-2 deletion approval: the experiment
effect controller (``run_guarded_effect`` / ``ExperimentEffectController``) and its only
dependency, the experiment run guard (``ExperimentRunGuard``). Neither was wired to any
experiment entry point.

These tests fail if one comes back (module, ``.py.bak`` copy, import or a reference under
nexus/ or scripts/, archive excluded), so re-adding is deliberate. The live pieces next to
them are pinned too: the fail-closed helper and its remaining migrated decision path.
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
REAPPEAR_SUFFIXES = (".py", ".py.bak")

RETIRED_MODULES = (
    "nexus.research.experiment_effect_controller",
    "nexus.research.experiment_run_guard",
)

RETIRED_NAMES = (
    "run_guarded_effect",
    "ExperimentEffectController",
    "ExperimentRunGuard",
    "ExperimentRunContract",
    "ExperimentRunLease",
    "RunEffectConflict",
)


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
    for module in RETIRED_MODULES:
        alternatives.append(rf"\b{re.escape(module)}\b")
        alternatives.append(rf"\b{re.escape(module.replace('.', '/'))}\b")
    alternatives.extend(rf"\b{re.escape(name)}\b" for name in RETIRED_NAMES)
    return re.compile("|".join(alternatives))


@pytest.mark.parametrize("module", RETIRED_MODULES)
def test_retired_phase2_item3_path_absent(module: str) -> None:
    base = REPO_ROOT / module.replace(".", "/")
    candidates = [base] + [base.with_name(base.name + suffix) for suffix in REAPPEAR_SUFFIXES]
    present = [str(p.relative_to(REPO_ROOT)) for p in candidates if p.exists()]
    assert present == [], f"retired in #2584 but present again: {present}"


@pytest.mark.parametrize("module", RETIRED_MODULES)
def test_retired_phase2_item3_module_not_importable(module: str) -> None:
    try:
        spec = importlib.util.find_spec(module)
    except ModuleNotFoundError:
        spec = None
    assert spec is None, f"{module} was retired (Issue #2584) but is importable again"


def test_retired_phase2_item3_not_imported() -> None:
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


def test_retired_phase2_item3_not_named() -> None:
    pattern = _name_pattern()
    offenders: list[str] = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {match.group(0)}")
    assert offenders == []


def test_phase2_item3_live_neighbours_kept() -> None:
    """The fail-closed helper the controller used stays, with its remaining decision path."""
    from nexus.contracts.fail_closed import decide, decide_all
    from tests.contracts.test_fail_closed_inventory import DECISION_PATHS

    assert callable(decide) and callable(decide_all)
    assert "nexus.core.capability_executor_registry:_exec_committee" in DECISION_PATHS
    assert not any(key.startswith("nexus.research.experiment_") for key in DECISION_PATHS)


def test_retired_phase2_item3_guard_detects_reference() -> None:
    """The scans are not vacuous: each import or naming form of a retired item is flagged."""
    sample = REPO_ROOT / "nexus" / "research" / "sample.py"
    for source in (
        "import nexus.research.experiment_run_guard\n",
        "from nexus.research import experiment_effect_controller\n",
        "from .experiment_run_guard import ExperimentRunGuard\n",
        "importlib.import_module('nexus.research.experiment_effect_controller')\n",
    ):
        names = _imported_modules(sample, ast.parse(source))
        assert any(_is_retired(name) for name in names), source
    for source in (
        "from nexus.contracts.fail_closed import decide\n",
        "from .contamination_guard import ContaminationGuard\n",
    ):
        names = _imported_modules(sample, ast.parse(source))
        assert not any(_is_retired(name) for name in names), source
    pattern = _name_pattern()
    assert pattern.search("run_guarded_effect(contract=contract)")
    assert pattern.search("guard = ExperimentRunGuard(state_root)")
    assert pattern.search("see nexus/research/experiment_effect_controller.py")
    # live names next to the retired ones are not flagged
    assert not pattern.search("decision = decide(checks)")
    assert not pattern.search("from nexus.research.contamination_guard import x")
