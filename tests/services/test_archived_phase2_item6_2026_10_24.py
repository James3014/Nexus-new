"""Guard for the 2026-10-24 Phase-2 retirement of item 6 (Issue #2584).

See ARCHIVED_2026-10-24_phase2_item6.md. Deleted on the Owner's decision of 2026-10-24
("delete as recommended": archive the design to knowledge first, then delete from Nexus-new,
not moved into Cairnwork) under the standing Phase-2 deletion approval: the GitHub completion
loop ``run_github_completion_loop`` and its ``GitHubCompletionPort``. It was never wired to
production; real merges use ``gh pr merge --match-head-commit`` behind required checks.

These tests fail if it comes back (module, ``.py.bak`` copy, import or a reference under
nexus/ or scripts/, archive excluded), so re-adding is deliberate. The live pieces it imported
are pinned too: the GitHub orchestration contracts and evaluator, and the issue closure guard.
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

RETIRED_MODULES = ("nexus.orchestrator.github_completion_loop",)

RETIRED_NAMES = (
    "run_github_completion_loop",
    "GitHubCompletionPort",
    "CompletionLoopOutcome",
    "CompletionLoopResult",
    "CasMergeStatus",
    "CasMergeResult",
    "DimensionRevalidationReceipt",
    "make_dimension_revalidation_receipt",
    "IntegrationMaterializationResult",
    "PostMergeReconciliationResult",
    "FinalMergeFields",
    "HeadCheckRunObservation",
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
def test_retired_phase2_item6_path_absent(module: str) -> None:
    base = REPO_ROOT / module.replace(".", "/")
    candidates = [base] + [base.with_name(base.name + suffix) for suffix in REAPPEAR_SUFFIXES]
    present = [str(p.relative_to(REPO_ROOT)) for p in candidates if p.exists()]
    assert present == [], f"retired in #2584 but present again: {present}"


@pytest.mark.parametrize("module", RETIRED_MODULES)
def test_retired_phase2_item6_module_not_importable(module: str) -> None:
    try:
        spec = importlib.util.find_spec(module)
    except ModuleNotFoundError:
        spec = None
    assert spec is None, f"{module} was retired (Issue #2584) but is importable again"


def test_retired_phase2_item6_not_imported() -> None:
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


def test_retired_phase2_item6_not_named() -> None:
    pattern = _name_pattern()
    offenders: list[str] = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {match.group(0)}")
    assert offenders == []


def test_phase2_item6_live_neighbours_kept() -> None:
    """What the retired loop imported stays live (production users outside the loop)."""
    from nexus.contracts.github_orchestration import (
        GitHubOrchestrationEvidence,
        MainMovementEvidence,
        MergeIntent,
    )
    from nexus.orchestrator.github_orchestration import (
        requalify_main_movement,
        resolve_durable_merge_authorization,
    )
    from nexus.services.issue_closure_guard import (
        IssueClosureIntentError,
        validate_final_merge_intent_binding,
    )

    for obj in (GitHubOrchestrationEvidence, MainMovementEvidence, MergeIntent):
        assert isinstance(obj, type), obj
    assert callable(requalify_main_movement)
    assert callable(resolve_durable_merge_authorization)
    assert callable(validate_final_merge_intent_binding)
    assert issubclass(IssueClosureIntentError, Exception)


def test_retired_phase2_item6_guard_detects_reference() -> None:
    """The scans are not vacuous: each import or naming form of the retired loop is flagged."""
    sample = REPO_ROOT / "nexus" / "orchestrator" / "sample.py"
    for source in (
        "import nexus.orchestrator.github_completion_loop\n",
        "from nexus.orchestrator import github_completion_loop\n",
        "from .github_completion_loop import run_github_completion_loop\n",
        "importlib.import_module('nexus.orchestrator.github_completion_loop')\n",
    ):
        names = _imported_modules(sample, ast.parse(source))
        assert any(_is_retired(name) for name in names), source
    for source in (
        "from nexus.orchestrator.github_orchestration import requalify_main_movement\n",
        "from .github_orchestration import resolve_durable_merge_authorization\n",
    ):
        names = _imported_modules(sample, ast.parse(source))
        assert not any(_is_retired(name) for name in names), source
    pattern = _name_pattern()
    assert pattern.search("result = run_github_completion_loop(initial_evidence=ev)")
    assert pattern.search("class Port(GitHubCompletionPort):")
    assert pattern.search("see nexus/orchestrator/github_completion_loop.py")
    # live names next to the retired ones are not flagged
    assert not pattern.search("from nexus.orchestrator.github_orchestration import x")
    assert not pattern.search("validate_final_merge_intent_binding(body)")
