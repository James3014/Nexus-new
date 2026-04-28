from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from nexus.orchestrator.task_contract import EvidenceRequirement
from nexus.orchestrator.task_contract import Task


def task_requires_code_impact(task: Task) -> bool:
    code_suffixes = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java")
    return any(str(path).endswith(code_suffixes) for path in task.allowed_files)


def _report_paths_for(task: Task, requirement: EvidenceRequirement) -> list[str]:
    paths: list[str] = []
    for evidence in task.evidence_list:
        if not evidence.satisfies(requirement):
            continue
        if evidence.artifact_path:
            paths.append(evidence.artifact_path)
        try:
            parts = shlex.split(evidence.command)
        except ValueError:
            parts = evidence.command.split()
        for index, part in enumerate(parts):
            if part == "--report-file" and index + 1 < len(parts):
                paths.append(parts[index + 1])
    return paths


def _has_codeintel_report(task: Task, requirement: EvidenceRequirement) -> bool:
    for report_path in _report_paths_for(task, requirement):
        path = Path(report_path)
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("schema_version") == "codeintel-v1":
            return True
    return False


def code_scan_report_paths(task: Task) -> list[str]:
    return _report_paths_for(task, EvidenceRequirement.CODE_SCAN)


def code_impact_report_paths(task: Task) -> list[str]:
    return _report_paths_for(task, EvidenceRequirement.CODE_IMPACT)


def has_code_scan_report(task: Task) -> bool:
    return _has_codeintel_report(task, EvidenceRequirement.CODE_SCAN)


def has_code_impact_report(task: Task) -> bool:
    return _has_codeintel_report(task, EvidenceRequirement.CODE_IMPACT)


def codeintel_artifacts(task: Task) -> dict[str, Any]:
    return {
        "schema_version": "codeintel-v1",
        "scan_reports": code_scan_report_paths(task),
        "impact_reports": code_impact_report_paths(task),
        "scan_report_valid": has_code_scan_report(task),
        "impact_report_valid": has_code_impact_report(task),
    }


def missing_pre_gate_requirements(task: Task) -> list[str | EvidenceRequirement]:
    deferred = {
        EvidenceRequirement.ACCEPTANCE_CHECK,
        EvidenceRequirement.DELIVERY_GATE,
    }
    missing = [
        requirement
        for requirement in task.missing_evidence_requirements()
        if requirement not in deferred
    ]
    if (
        task_requires_code_impact(task)
        and EvidenceRequirement.CODE_SCAN not in missing
        and not has_code_scan_report(task)
    ):
        missing.append(EvidenceRequirement.CODE_SCAN)
    if (
        task_requires_code_impact(task)
        and EvidenceRequirement.CODE_IMPACT not in missing
        and not has_code_impact_report(task)
    ):
        missing.append(EvidenceRequirement.CODE_IMPACT)
    return missing


def missing_claim_requirements(task: Task) -> list[str | EvidenceRequirement]:
    missing = list(task.missing_evidence_requirements())
    if (
        task_requires_code_impact(task)
        and EvidenceRequirement.CODE_SCAN not in missing
        and not has_code_scan_report(task)
    ):
        missing.append(EvidenceRequirement.CODE_SCAN)
    if (
        task_requires_code_impact(task)
        and EvidenceRequirement.CODE_IMPACT not in missing
        and not has_code_impact_report(task)
    ):
        missing.append(EvidenceRequirement.CODE_IMPACT)
    return missing


def pytest_artifacts(task: Task) -> list[str]:
    return [
        evidence.output_summary
        for evidence in task.evidence_list
        if evidence.kind.value == "pytest" and evidence.output_summary
    ]


def build_temp_evidence_payload(task: Task) -> dict[str, Any]:
    return {
        "final_response": "Automated verification",
        "evidence_bundle": {
            "code_artifacts": task.allowed_files,
            "test_artifacts": pytest_artifacts(task),
            "command_artifacts": [e.command for e in task.evidence_list],
            "codeintel_artifacts": codeintel_artifacts(task),
        },
    }


def derive_claim_bundle(task: Task, final_response: str, diff: str) -> dict[str, Any]:
    has_proof = bool(diff and diff.strip())
    all_passed = all(e.exit_code == 0 for e in task.evidence_list)
    evidence_count = len(task.evidence_list)
    missing_requirements = missing_claim_requirements(task)

    if (
        not missing_requirements
        and all_passed
        and has_proof
        and evidence_count >= len(task.evidence_requirements)
    ):
        confidence = "HIGH"
        claim_state = "VERIFIED"
    elif not missing_requirements and all_passed and evidence_count > 0:
        confidence = "MEDIUM"
        claim_state = "PARTIAL"
    else:
        confidence = "LOW"
        claim_state = "UNVERIFIED"

    return {
        "final_response": final_response,
        "claim_state": claim_state,
        "confidence_level": confidence,
        "proof_type": "git_diff" if has_proof else "none",
        "proof_value": diff if has_proof else "no_physical_changes_detected",
        "unmet_evidence_requirements": missing_requirements,
        "evidence_bundle": {
            "code_artifacts": task.allowed_files,
            "test_artifacts": pytest_artifacts(task),
            "command_artifacts": [
                f"{e.command} (exit: {e.exit_code})" for e in task.evidence_list
            ],
            "codeintel_artifacts": codeintel_artifacts(task),
        },
    }
