"""Gate inputs for the sprint's UnifiedRuntime request (wiring PR-4).

The preflight gates (pregate, harness_preflight_sensor, plan_quality_gate, mempalace_gate,
memory, codeintel) refuse with a missing-input code when the request carries no inputs.  The
sprint already knows every input they need from its own task contract: the task statement,
the target file, and the visible test with the exact pytest command the sprint runs on it.
This module derives those inputs (never from a hidden test) and records where each came from.

Inputs travel through the existing request objects only: ``request.codeintel`` (the keys the
registry invoker already reads, same shapes as ``nexus/engine/canonical_task_seam.py``) and
``route["workspace_root"]``.  None of these keys is rendered into the model prompt: the
CodeIntel prompt summary reads other fields, and the strict lane withholds the gates'
verdicts from the evidence block (``online_nexus_context``).
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
import shlex
from pathlib import Path
from typing import Any, Mapping

GATE_INPUTS_ENV = "NEXUS_SPRINT_GATE_INPUTS"
GATE_INPUT_PROVENANCE_KEY = "gate_input_provenance"
MEMPALACE_TENANT = "sprint-task-contract"
MEMPALACE_ARTIFACT_TYPE = "sprint_task_contract"
VERIFY_TIMEOUT_SEC = 60
# Capabilities whose missing inputs this module supplies.  In the strict (symmetric) lane their
# verdicts are withheld from the model prompt (online_nexus_context).
FED_CAPABILITIES: frozenset[str] = frozenset({
    "pregate",
    "harness_preflight_sensor",
    "plan_quality_gate",
    "mempalace_gate",
    "memory",
    "codeintel",
})
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def gate_inputs_enabled() -> bool:
    """On unless ``NEXUS_SPRINT_GATE_INPUTS`` is set to a false value."""

    raw = os.environ.get(GATE_INPUTS_ENV, "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def target_symbol_from_visible_test(source_code: str, test_source: str) -> str:
    """First top-level function/class of the target source that the visible test names."""

    if not source_code.strip() or not test_source.strip():
        return ""
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return ""
    referenced = set(_WORD_RE.findall(test_source))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in referenced:
                return node.name
    return ""


def _route_risk_score(route: Mapping[str, Any] | None) -> int | None:
    if not isinstance(route, Mapping):
        return None
    features = route.get("route_features")
    for source in (features if isinstance(features, Mapping) else {}, route):
        value = source.get("risk_score")
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return int(value)
    return None


def sprint_gate_inputs(
    *,
    repo_root: Path,
    task: str,
    target_file: str,
    test_file: str,
    source_code: str = "",
    route: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return ``{"codeintel": {...}, "workspace_root": str}`` for one sprint request.

    ``codeintel[GATE_INPUT_PROVENANCE_KEY]`` maps every supplied input to its source.  An input
    that cannot be derived honestly is omitted, so its gate keeps refusing with its
    missing-input code instead of evaluating invented data.
    """

    # Imported lazily: sprint_service imports this module.
    from nexus.research.sprint_service import visible_test_pytest_cmd, visible_test_target_error

    root = Path(repo_root).resolve()
    target = str(target_file or "").strip()
    test = str(test_file or "").strip()
    task_text = str(task or "")
    provenance: dict[str, str] = {}
    codeintel: dict[str, Any] = {"workspace_root": str(root)}
    provenance["workspace_root"] = "sprint.repo_root"

    target_path = root / target if target else None
    target_exists = bool(
        target
        and target_path is not None
        and not Path(target).is_absolute()
        and ".." not in Path(target).parts
        and target_path.is_file()
    )
    if target_exists:
        codeintel["target_file"] = target
        codeintel["search_paths"] = [target]
        provenance["target_file"] = "sprint.config.target_file"
        provenance["search_paths"] = "sprint.config.target_file"

    # Visible test only: visible_test_target_error() refuses test_hidden*, directories,
    # symlinks, option-like and out-of-repo paths, so a hidden test is never named here.
    test_error = visible_test_target_error(root, test) if test else "missing_test_file"
    test_source = ""
    verify_command = ""
    if not test_error:
        test_source = (root / test).read_text(encoding="utf-8", errors="replace")
        verify_command = shlex.join(visible_test_pytest_cmd(test))
        codeintel["verify_commands"] = [verify_command]
        codeintel["verify_timeout_sec"] = VERIFY_TIMEOUT_SEC
        provenance["verify_commands"] = "sprint.visible_test_pytest_cmd(config.test_file)"
        provenance["verify_timeout_sec"] = "gate_inputs.VERIFY_TIMEOUT_SEC"

    if target_exists and test_source:
        source = source_code or target_path.read_text(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        symbol = target_symbol_from_visible_test(source, test_source)
        if symbol:
            codeintel["target_symbol"] = symbol
            provenance["target_symbol"] = "visible_test_reference_to_target_definition"

    # Plan-quality context from the task contract (no planner fabrication).
    checks = {
        "task_statement_present": bool(task_text.strip()),
        "target_file_exists": target_exists,
        "visible_test_valid": not test_error,
        "verify_command_present": bool(verify_command),
    }
    codeintel["intent_pass"] = bool(
        checks["task_statement_present"] and checks["target_file_exists"]
    )
    codeintel["handoff_readiness"] = round(sum(checks.values()) / len(checks), 4)
    provenance["intent_pass"] = "task_contract:task_statement_present+target_file_exists"
    provenance["handoff_readiness"] = "task_contract:fraction_of_checks(" + ",".join(checks) + ")"
    # risk_score is read by the plan-quality invoker from the request route (route_features),
    # never copied into codeintel: the CodeIntel prompt summary renders codeintel.risk_score.
    if _route_risk_score(route) is not None:
        provenance["risk_score"] = "flow_route.route_features.risk_score"
    if target_exists:
        codeintel["target_files"] = [target]
        codeintel["deliverables"] = [target]
        provenance["target_files"] = "sprint.config.target_file"
        provenance["deliverables"] = "sprint.config.target_file"
        steps = [f"apply one model edit to {target}"]
        if verify_command:
            steps.append(f"run the visible test {test}")
        codeintel["steps"] = steps
        provenance["steps"] = "sprint.procedure(edit_target,run_visible_test)"
    if target_exists and not test_error:
        codeintel["acceptance_criteria"] = [f"visible test {test} passes"]
        codeintel["impact_map"] = {"edges": [{"source": target, "covered_by": test}]}
        provenance["acceptance_criteria"] = "task_contract.visible_test"
        provenance["impact_map"] = "task_contract.visible_test_covers_target"

    # MemPalace artifact: the task contract itself (hashes and paths, no answer text).
    if target_exists and task_text.strip():
        artifact_id = (
            "sprint-contract-"
            + _sha256("\n".join((task_text, target, test, _sha256(test_source))))[:24]
        )
        codeintel["mempalace_tenant_id"] = MEMPALACE_TENANT
        codeintel["mempalace_artifact_type"] = MEMPALACE_ARTIFACT_TYPE
        codeintel["mempalace_artifact"] = {
            "artifact_id": artifact_id,
            "task_statement_sha256": _sha256(task_text),
            "target_file": target,
            "visible_test_file": test if not test_error else "",
            "visible_test_sha256": _sha256(test_source) if test_source else "",
        }
        codeintel["mempalace_query"] = artifact_id
        for key in (
            "mempalace_tenant_id",
            "mempalace_artifact_type",
            "mempalace_artifact",
            "mempalace_query",
        ):
            provenance[key] = "task_contract.artifact"

    codeintel[GATE_INPUT_PROVENANCE_KEY] = provenance
    return {"codeintel": codeintel, "workspace_root": str(root)}
