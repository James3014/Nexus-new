from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable

from nexus.services.local_heal.local_model_patch_envelope import LocalModelPatchEnvelope


@dataclass(frozen=True)
class LocalModelApplyDryRunReceipt:
    task_id: str
    candidate_id: str
    selected_candidate_hash: str
    applied_patch_hash: str = ""
    selected_candidate_hash_matches_applied: bool = False
    candidate_output_isolated: bool = False
    patch_apply_status: str = "not_run"
    patch_apply_error: str = ""
    mutation_allowed: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False


def run_local_model_apply_dry_run(
    envelope: LocalModelPatchEnvelope,
    *,
    apply_fn: Callable[[LocalModelPatchEnvelope], str] | None = None,
) -> LocalModelApplyDryRunReceipt:
    
    if envelope.parser_status != "pass":
        return LocalModelApplyDryRunReceipt(
            task_id=envelope.task_id,
            candidate_id=envelope.candidate_id,
            selected_candidate_hash=envelope.candidate_hash,
            patch_apply_status="blocked",
            patch_apply_error=f"parser_blocked: {envelope.parser_error}",
        )
        
    if apply_fn is None:
        return LocalModelApplyDryRunReceipt(
            task_id=envelope.task_id,
            candidate_id=envelope.candidate_id,
            selected_candidate_hash=envelope.candidate_hash,
            patch_apply_status="blocked",
            patch_apply_error="apply_fn_missing",
            candidate_output_isolated=False,
            applied_patch_hash="",
            selected_candidate_hash_matches_applied=False,
        )
        
    try:
        applied_result = apply_fn(envelope)
        applied_hash = hashlib.sha256(applied_result.encode("utf-8")).hexdigest()
        
        matches = (applied_hash == envelope.candidate_hash)
        
        return LocalModelApplyDryRunReceipt(
            task_id=envelope.task_id,
            candidate_id=envelope.candidate_id,
            selected_candidate_hash=envelope.candidate_hash,
            applied_patch_hash=applied_hash,
            selected_candidate_hash_matches_applied=matches,
            candidate_output_isolated=True,
            patch_apply_status="applied",
            mutation_allowed=False, # 始終保持 False，由外層決策控制
        )
    except Exception as e:
        return LocalModelApplyDryRunReceipt(
            task_id=envelope.task_id,
            candidate_id=envelope.candidate_id,
            selected_candidate_hash=envelope.candidate_hash,
            patch_apply_status="blocked",
            patch_apply_error=f"apply_error: {str(e)}",
        )
