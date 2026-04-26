from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexus.delivery.receipt import load_delivery_receipt


@dataclass(frozen=True)
class SubmissionAssessment:
    delivery_gate_passed: bool
    acceptance_gate_passed: bool
    claim_state: str
    proof_present: bool
    receipt_path: str | None

    @property
    def passed(self) -> bool:
        return (
            self.claim_state == "VERIFIED"
            and self.delivery_gate_passed
            and self.acceptance_gate_passed
        )

    @property
    def phantom_blocked(self) -> bool:
        return not self.passed

    @property
    def gate_summary(self) -> dict[str, Any]:
        return {
            "delivery_gate": "PASS" if self.delivery_gate_passed else "FAIL",
            "acceptance_check": "PASS" if self.acceptance_gate_passed else "FAIL",
            "hallucination_index": self.claim_state,
            "contract_check": "UNRUN",
            "ci_gate": "UNRUN",
            "proof_present": self.proof_present,
        }

def assess_submission(
    *,
    receipt_payload: dict[str, Any],
    derived_bundle: dict[str, Any],
    receipt_path: Path,
) -> SubmissionAssessment:
    return SubmissionAssessment(
        delivery_gate_passed=bool(receipt_payload.get("delivery_gate_passed", False)),
        acceptance_gate_passed=bool(
            (receipt_payload.get("acceptance_result") or {}).get("gate_passed", False)
        ),
        claim_state=str(derived_bundle.get("claim_state", "UNVERIFIED")),
        proof_present=str(derived_bundle.get("confidence_level", "")).upper() == "HIGH",
        receipt_path=str(receipt_path) if receipt_payload else None,
    )


def build_submission_payload(
    *,
    commit_sha: str,
    assessment: SubmissionAssessment,
) -> dict[str, Any]:
    return {
        "commit_sha": commit_sha,
        "nas_fitness": 1.0 if assessment.claim_state == "VERIFIED" else 0.5,
        "nexus_participation_ratio": 1.0,
        "swarm_pids": "none",
        "gate_summary": assessment.gate_summary,
        "receipt_path": assessment.receipt_path,
    }


def governance_payload(task_id: str, assessment: SubmissionAssessment) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "pass": assessment.passed,
        "phantom_blocked": assessment.phantom_blocked,
        "proof_present": assessment.proof_present,
    }
