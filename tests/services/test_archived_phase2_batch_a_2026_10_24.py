"""Guard for the 2026-10-24 Phase-2 dead-code retirement (batch A, Issue #2584).

See ARCHIVED_2026-10-24_phase2_batch_A.md. Deleted under the Owner's standing Phase-2
deletion approval (2026-10-20):

* the operator outcome receipt: ``SelfHostedTaskService.record_operator_outcome``
  (``self_hosted_task_service_parts/operator_outcome.py``) and its contract module
  ``nexus/contracts/operator_outcome_receipt.py``;
* ``SelfHostedTaskService._heartbeat`` (the live heartbeat loop is nexus-runtime's; it
  reaches ``_touch_owned_state`` through ``runtime_coordination_bridge``, which stays);
* ``TargetIntegrationLifecycle.transactional_integration`` and its receipt type.

These tests fail if one comes back (module, member or a reference under nexus/ or
scripts/, archive excluded), so re-adding is deliberate. The live pieces next to them
are pinned too: ``_touch_owned_state``, the bridge heartbeat and the integration sink.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("nexus", "scripts")
SCAN_EXCLUDED_PREFIXES = ("scripts/archive/",)
TEXT_SUFFIXES = {".py", ".json", ".txt", ".toml", ".yaml", ".yml", ".cfg", ".ini", ".sh"}

RETIRED_MODULES = (
    "nexus.contracts.operator_outcome_receipt",
    "nexus.orchestrator.self_hosted_task_service_parts.operator_outcome",
)

# (module, class, member) that must stay absent.
RETIRED_MEMBERS = (
    ("nexus.orchestrator.self_hosted_task_service", "SelfHostedTaskService", "record_operator_outcome"),
    ("nexus.orchestrator.self_hosted_task_service", "SelfHostedTaskService", "_heartbeat"),
    ("nexus.orchestrator.target_integration_lifecycle", "TargetIntegrationLifecycle", "transactional_integration"),
)

RETIRED_NAMES = (
    "record_operator_outcome",
    "_OperatorOutcomeMixin",
    "OperatorOutcomeReceipt",
    "build_operator_outcome_receipt",
    "validate_operator_outcome_receipt",
    "transactional_integration",
    "IntegrationExecutionReceipt",
)

RETIRED_CONTRACT_ATTRS = (
    ("nexus.contracts.target_integration_lifecycle", "IntegrationExecutionReceipt"),
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
def test_retired_phase2_batch_a_path_absent(module: str) -> None:
    base = REPO_ROOT / module.replace(".", "/")
    present = [
        str(p.relative_to(REPO_ROOT))
        for p in (base, base.with_name(base.name + ".py"))
        if p.exists()
    ]
    assert present == [], f"retired in #2584 but present again: {present}"


@pytest.mark.parametrize("module", RETIRED_MODULES)
def test_retired_phase2_batch_a_module_not_importable(module: str) -> None:
    try:
        spec = importlib.util.find_spec(module)
    except ModuleNotFoundError:
        spec = None
    assert spec is None, f"{module} was retired (Issue #2584) but is importable again"


@pytest.mark.parametrize(
    ("module", "cls", "member"), RETIRED_MEMBERS, ids=[m for _, _, m in RETIRED_MEMBERS]
)
def test_retired_phase2_batch_a_member_absent(module: str, cls: str, member: str) -> None:
    owner = getattr(importlib.import_module(module), cls)
    assert not hasattr(owner, member), f"{cls}.{member} was retired (Issue #2584)"


def test_retired_phase2_batch_a_contract_attrs_absent() -> None:
    for module, name in RETIRED_CONTRACT_ATTRS:
        assert not hasattr(importlib.import_module(module), name), name


def test_retired_phase2_batch_a_not_imported() -> None:
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


def test_retired_phase2_batch_a_not_named() -> None:
    pattern = _name_pattern()
    offenders: list[str] = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {match.group(0)}")
    assert offenders == []


def test_phase2_batch_a_live_neighbours_kept() -> None:
    """What the retired code sat next to and the live path still uses."""
    from nexus.orchestrator.governed_integration import ControlledIntegrationManager
    from nexus.orchestrator.runtime_coordination_bridge import _State
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
    from nexus.orchestrator.target_integration_lifecycle import TargetIntegrationLifecycle

    assert isinstance(
        inspect.getattr_static(SelfHostedTaskService, "_touch_owned_state"), staticmethod
    )
    assert callable(_State.heartbeat)
    assert callable(SelfHostedTaskService.integrate_approved)
    assert callable(ControlledIntegrationManager.integrate_authorized_task_state)
    for member in ("build_preview", "authorize", "cleanup_target", "persist_receipt"):
        assert callable(getattr(TargetIntegrationLifecycle, member)), member
    # historical task states may still carry the receipt fields; the read
    # projection keeps hiding them from detailed snapshots
    source = (
        REPO_ROOT / "nexus/orchestrator/self_hosted_task_service_parts/read_projection.py"
    ).read_text(encoding="utf-8")
    assert source.count('"operator_outcome_receipts"') >= 3


def test_retired_phase2_batch_a_guard_detects_reference() -> None:
    """The scans are not vacuous: each import or naming form of a retired item is flagged."""
    sample = REPO_ROOT / "nexus" / "orchestrator" / "self_hosted_task_service_parts" / "sample.py"
    for source in (
        "import nexus.contracts.operator_outcome_receipt\n",
        "from nexus.contracts import operator_outcome_receipt\n",
        "from .operator_outcome import _OperatorOutcomeMixin\n",
        "importlib.import_module('nexus.orchestrator.self_hosted_task_service_parts.operator_outcome')\n",
    ):
        names = _imported_modules(sample, ast.parse(source))
        assert any(_is_retired(name) for name in names), source
    for source in (
        "from .read_projection import _ReadProjectionMixin\n",
        "from nexus.contracts.target_integration_lifecycle import CleanupDecision\n",
    ):
        names = _imported_modules(sample, ast.parse(source))
        assert not any(_is_retired(name) for name in names), source
    pattern = _name_pattern()
    assert pattern.search("service.record_operator_outcome(task_id, receipt)")
    assert pattern.search("TargetIntegrationLifecycle.transactional_integration(")
    assert pattern.search("see nexus/contracts/operator_outcome_receipt.py")
    assert pattern.search("-> IntegrationExecutionReceipt:")
    # live names next to the retired ones are not flagged
    assert not pattern.search('state.pop("operator_outcome_receipts", None)')
    assert not pattern.search("ControlledIntegrationManager.integrate_authorized_task_state")
    assert not pattern.search("self.service._touch_owned_state(state, attempt_id)")
