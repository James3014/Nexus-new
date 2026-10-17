"""Guard for the 2026-10-17 dead-code retirement (batch B3, Issue #2491).

See ARCHIVED_2026-10-17_deadcode_b3.md. The modules below were physically deleted
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

PACKAGE = "nexus.services.local_heal"
RETIRED_NAMES = (
    "abbreviated_traceback",
    "assertion_extractor",
    "ast_locator",
    "candidate_generation",
    "concurrency",
    "degradation_controller",
    "effect_ledger",
    "evaluator",
    "evidence_freeze",
    "export_guard",
    "function_localizer",
    "fuzzy_spec_registry",
    "heterogeneous_candidate_provider",
    "hunk_localizer",
    "judge_selector",
    "linear_replay_runner",
    "local_model_capability_executor_registry",
    "local_qwen_evidence_gate",
    "memory_belief_signal",
    "micromerger",
    "parser",
    "patch_intent",
    "pre_patch",
    "protocol_transition_receipt",
    "quota_monitor",
    "repro_preflight",
    "runbook_compliance",
    "runbook_compliance_cli",
    "sandbox",
    "shadow_receipt",
    "source_hash_guard",
    "strategy_conditioned_packer",
    "strategy_differentiator",
    "swarm_committee_bridge",
    "verifier_replay_gate",
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
def test_retired_deadcode_b3_path_absent(name: str) -> None:
    base = REPO_ROOT / PACKAGE_DIR / name
    present = [
        str(p.relative_to(REPO_ROOT))
        for p in (base, *(base.with_suffix(s) for s in REAPPEAR_SUFFIXES))
        if p.exists()
    ]
    assert present == [], f"retired in #2491 but present again: {present}"


@pytest.mark.parametrize("module", RETIRED_MODULES)
def test_retired_deadcode_b3_module_not_importable(module: str) -> None:
    try:
        spec = importlib.util.find_spec(module)
    except ModuleNotFoundError:
        spec = None
    assert spec is None, f"{module} was retired (Issue #2491) but is importable again"


def test_retired_deadcode_b3_not_imported() -> None:
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


def test_retired_deadcode_b3_not_named() -> None:
    pattern = _name_pattern()
    offenders: list[str] = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {match.group(0)}")
    assert offenders == []


def test_retired_deadcode_b3_guard_detects_reference() -> None:
    """The scans are not vacuous: each import or naming form of a retired module is flagged."""
    sample = REPO_ROOT / "nexus" / "services" / "local_heal" / "sample.py"
    for source in (
        "import nexus.services.local_heal.parser\n",
        "from nexus.services.local_heal import sandbox\n",
        "from .runbook_compliance import check_lane_classification\n",
        "from ..local_heal.evaluator import PatchTreeEvaluator\n",
        "importlib.import_module('nexus.services.local_heal.quota_monitor')\n",
    ):
        names = _imported_modules(sample, ast.parse(source))
        assert any(_is_retired(name) for name in names), source
    for kept in (
        "from .anchored_edit import AnchoredEdit\n",
        "from .degradation_policy import evaluate_degradation_policy\n",
        "from .parser_utils import x\n",
    ):
        assert not any(_is_retired(name) for name in _imported_modules(sample, ast.parse(kept))), (
            kept
        )
    pattern = _name_pattern()
    assert pattern.search('{"module": "nexus.services.local_heal.shadow_receipt"}')
    assert pattern.search("see nexus/services/local_heal/export_guard.py")
    assert not pattern.search(
        "nexus.services.local_heal.telemetry and nexus/services/local_heal/sandbox_v2"
    )
