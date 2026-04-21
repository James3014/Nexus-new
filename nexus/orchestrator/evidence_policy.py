from __future__ import annotations

from typing import Any

from nexus.orchestrator.task_contract import EvidenceRequirement
from nexus.orchestrator.task_contract import Task


def missing_pre_gate_requirements(task: Task) -> list[str | EvidenceRequirement]:
    deferred = {
        EvidenceRequirement.ACCEPTANCE_CHECK,
        EvidenceRequirement.DELIVERY_GATE,
    }
    return [
        requirement
        for requirement in task.missing_evidence_requirements()
        if requirement not in deferred
    ]


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
        },
    }


def derive_claim_bundle(task: Task, final_response: str, diff: str) -> dict[str, Any]:
    has_proof = bool(diff and diff.strip())
    all_passed = all(e.exit_code == 0 for e in task.evidence_list)
    evidence_count = len(task.evidence_list)
    missing_requirements = task.missing_evidence_requirements()

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
        },
    }
