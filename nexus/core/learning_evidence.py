from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .state_contracts import NexusState


@dataclass(frozen=True)
class LearningEvidence:
    success: bool
    phases: List[str]
    unique_phase_count: int
    retry_count: int
    policy_hit_count: int
    patch_generated: bool
    patch_apply_success: bool
    proof_present: bool
    proof_type: str
    proof_value: str


class LearningEvidenceBuilder:
    _VALID_PROOF_TYPES = {"git_diff", "git_diff_checksum", "checksum"}

    @staticmethod
    def build(state: NexusState) -> LearningEvidence:
        phases = [step.phase for step in state.steps_history]
        unique_phase_count = len(set(phases))

        pipeline_success = state.metadata.get("pipeline_success")
        if isinstance(pipeline_success, bool):
            success = pipeline_success
        else:
            review_status = str(state.metadata.get("last_review_status", "")).upper()
            success = review_status == "APPROVED" or state.health_score > 80.0

        metadata = state.metadata
        patch_generated = _as_bool(
            metadata.get("last_patch_generated", metadata.get("patch_generated", False))
        )
        patch_apply_success = _as_bool(
            metadata.get("last_patch_apply_success", metadata.get("patch_apply_success", False))
        )
        proof_type = str(metadata.get("last_proof_type", metadata.get("proof_type", "")) or "").strip()
        proof_value = str(metadata.get("last_proof_value", metadata.get("proof_value", "")) or "").strip()
        proof_present = bool(proof_type and proof_value and proof_type.lower() in LearningEvidenceBuilder._VALID_PROOF_TYPES)

        return LearningEvidence(
            success=success,
            phases=phases,
            unique_phase_count=unique_phase_count,
            retry_count=int(state.retry_count or 0),
            policy_hit_count=len(state.policy_hit_ids),
            patch_generated=patch_generated,
            patch_apply_success=patch_apply_success,
            proof_present=proof_present,
            proof_type=proof_type,
            proof_value=proof_value,
        )

    @staticmethod
    def build_episode(state: NexusState, evidence: LearningEvidence) -> Dict[str, object]:
        return {
            "task_id": state.task_id,
            "success": evidence.success,
            "cost": state.total_token_usage,
            "phases": evidence.phases,
            "policy_hit_ids": list(state.policy_hit_ids),
            "proof": {
                "required": bool(evidence.success and evidence.patch_generated and evidence.patch_apply_success),
                "present": evidence.proof_present,
                "type": evidence.proof_type,
                "value": evidence.proof_value,
            },
            "metadata": state.metadata,
        }


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() == "true"
