"""Guard for the 2026-10-17 dead-code retirement (batch B2, Issue #2514).

See ARCHIVED_2026-10-17_deadcode_b2.md. The modules below were physically deleted
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
    "degradation_policy",
    "four_stage_orchestrator",
    "local_model_apply_dry_run",
    "local_solve_dry_run_loop",
    "memory_action_receipt",
    "p3_authority_coupling",
    "p3_closeout_decision",
    "p3_cloud_candidate_stub",
    "p3_dry_run_invariants",
    "p3_dry_run_schema",
    "p3_local_cheap_verifier",
    "p3_local_cheap_verifier_runtime",
    "p3_local_diagnosis_runtime",
    "p3_p6_advisory_consumer",
    "p3_provider_readiness",
    "p3_shadow_invariants",
    "p3_shadow_orchestrator",
    "p3_shadow_promotion_policy",
    "p3_shadow_receipt",
    "p3_synthetic_e2e_trace",
    "p3_synthetic_provider",
    "p3_synthetic_provider_adapter",
    "p3_synthetic_provider_receipt",
    "p5_memory_bridge",
    "p5_p6_memory_context",
    "p5_selection_memory",
    "p6_closeout_decision",
    "p6_heldout_dry_run_harness",
    "p6_heldout_e2e_trace",
    "p6_heldout_monitor_adapter",
    "p6_heldout_planner",
    "p6_heldout_readiness",
    "p6_heldout_validator",
    "p6_mainline_boundary",
    "p6_p3_handoff_contract",
    "p6_p3_handoff_trace",
    "p6_receipt",
    "p6_rollout_canary",
    "p6_rollout_monitor",
    "p6_rollout_policy",
    "p6_rollout_receipt",
    "p6_runtime_hook",
    "p7_armor_evidence_manifest",
    "p7_armor_invariants",
    "p7_armor_readiness",
    "p7_armor_receipt",
    "p7_armor_synthetic_trace",
    "p8_c_authority_auditor",
    "p8_c_call_budget_auditor",
    "p8_c_p9_readiness",
    "p8_c_receipt_auditor",
    "p8_c_redaction_auditor",
    "p8_c_smoke_evidence_manifest",
    "p8_e_final_preflight",
    "p8_e_post_smoke_validator",
    "p8_human_approval_intake",
    "p8_network_smoke_approval",
    "p8_network_smoke_boundary",
    "p8_network_smoke_executor",
    "p8_network_smoke_receipt",
    "p8_one_call_lock",
    "p8_one_smoke_preflight",
    "p8_one_smoke_runner",
    "p8_post_smoke_validator",
    "p8_redaction_guard",
    "p8_smoke_prompt_capsule",
    "p8_smoke_result_validator",
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
def test_retired_deadcode_b2_path_absent(name: str) -> None:
    base = REPO_ROOT / PACKAGE_DIR / name
    present = [
        str(p.relative_to(REPO_ROOT))
        for p in (base, *(base.with_suffix(s) for s in REAPPEAR_SUFFIXES))
        if p.exists()
    ]
    assert present == [], f"retired in #2514 but present again: {present}"


@pytest.mark.parametrize("module", RETIRED_MODULES)
def test_retired_deadcode_b2_module_not_importable(module: str) -> None:
    try:
        spec = importlib.util.find_spec(module)
    except ModuleNotFoundError:
        spec = None
    assert spec is None, f"{module} was retired (Issue #2514) but is importable again"


def test_retired_deadcode_b2_not_imported() -> None:
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


def test_retired_deadcode_b2_not_named() -> None:
    pattern = _name_pattern()
    offenders: list[str] = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {match.group(0)}")
    assert offenders == []


def test_retired_deadcode_b2_guard_detects_reference() -> None:
    """The scans are not vacuous: each import or naming form of a retired module is flagged."""
    sample = REPO_ROOT / "nexus" / "services" / "local_heal" / "sample.py"
    for source in (
        "import nexus.services.local_heal.p8_one_smoke_runner\n",
        "from nexus.services.local_heal import p6_receipt\n",
        "from .degradation_policy import evaluate_degradation_policy\n",
        "from ..local_heal.four_stage_orchestrator import run\n",
        "importlib.import_module('nexus.services.local_heal.p3_shadow_orchestrator')\n",
    ):
        names = _imported_modules(sample, ast.parse(source))
        assert any(_is_retired(name) for name in names), source
    for kept in (
        "from .p3_local_retry_stub import compute_p3_local_retry_stub\n",
        "from .p3_local_retry_stub_runtime import x\n",
        "from .p3_local_diagnosis import compute_p3_local_diagnosis\n",
        "from .anchored_edit import AnchoredEdit\n",
    ):
        assert not any(_is_retired(name) for name in _imported_modules(sample, ast.parse(kept))), (
            kept
        )
    pattern = _name_pattern()
    assert pattern.search('{"module": "nexus.services.local_heal.p7_armor_receipt"}')
    assert pattern.search("see nexus/services/local_heal/p6_rollout_canary.py")
    assert not pattern.search(
        "nexus.services.local_heal.p3_local_retry_stub and nexus/services/local_heal/p6_receipt_v2"
    )
