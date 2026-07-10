from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from nexus.executors.cloud_executor_with_compact_prompt import RealCloudExecutor
from nexus.services.local_heal.p3_local_cheap_verifier_runtime import (
    RealLocalCheapVerifier,
)
from nexus.services.local_heal.p3_local_diagnosis_runtime import RealLocalDiagnosis
from nexus.services.local_heal.p3_local_retry_stub_runtime import RealLocalRetry


@dataclass(frozen=True)
class FourStageReceipt:
    task_id: str
    stage1_diagnosis_hash: str
    stage2_candidate_hash: str
    stage3_verifier_result: str
    stage4_retry_hash: str
    final_winner_hash: str
    stages_run: tuple[str, ...]
    failed_at_stage: str
    runtime_behavior_changed: bool = True
    public_claim_allowed: bool = False


class FourStageOrchestrator:
    def __init__(self) -> None:
        self.diagnosis = RealLocalDiagnosis()
        self.cloud_executor = RealCloudExecutor()
        self.cheap_verifier = RealLocalCheapVerifier()
        self.retry = RealLocalRetry()

    def run_four_stage(
        self,
        task_id: str,
        problem_statement: str,
        anchor: dict[str, Any],
        evidence_refs: tuple[str, ...] = (),
    ) -> FourStageReceipt:
        skeleton = {
            "task_id": task_id,
            "p3_failure_summary": problem_statement,
            "p3_task_difficulty": anchor.get("difficulty", "unknown"),
        }

        stage1 = self.diagnosis.compute_p3_local_diagnosis_runtime(skeleton, anchor)
        stage1_hash = stage1.compact_prompt_hash

        cloud_metadata = {
            "task_id": task_id,
            "p3_diagnosis_prompt": stage1.compact_prompt,
            "target_file": anchor.get("target_file", ""),
        }
        stage2 = self.cloud_executor.run_with_compact_prompt(
            prompt=stage1.compact_prompt,
            anchor=anchor,
        )
        stage2_hash = stage2.raw_output_hash

        verifier_metadata = {
            "task_id": task_id,
            "p3_candidate_prompt": stage2.raw_output,
            "p3_cloud_stub_candidate_generated": stage2.invoked,
        }
        stage3 = self.cheap_verifier.compute_p3_cheap_verifier_runtime(verifier_metadata)
        stage3_result = "pass" if stage3.cheap_verifier_result == "runtime_invoked" else "fail"

        if stage3_result == "pass":
            return FourStageReceipt(
                task_id=task_id,
                stage1_diagnosis_hash=stage1_hash,
                stage2_candidate_hash=stage2_hash,
                stage3_verifier_result=stage3_result,
                stage4_retry_hash="",
                final_winner_hash=stage2_hash,
                stages_run=("stage1", "stage2", "stage3"),
                failed_at_stage="",
            )

        retry_metadata = {
            "task_id": task_id,
            "p3_candidate_prompt": stage2.raw_output,
            "p3_cheap_verifier_result": stage3.cheap_verifier_result,
        }
        stage4 = self.retry.compute_p3_retry_stub_runtime(retry_metadata)
        stage4_hash = stage4.retry_candidate_hash

        if stage4.retry_candidate_generated:
            return FourStageReceipt(
                task_id=task_id,
                stage1_diagnosis_hash=stage1_hash,
                stage2_candidate_hash=stage2_hash,
                stage3_verifier_result=stage3_result,
                stage4_retry_hash=stage4_hash,
                final_winner_hash=stage4_hash,
                stages_run=("stage1", "stage2", "stage3", "stage4"),
                failed_at_stage="",
            )

        return FourStageReceipt(
            task_id=task_id,
            stage1_diagnosis_hash=stage1_hash,
            stage2_candidate_hash=stage2_hash,
            stage3_verifier_result=stage3_result,
            stage4_retry_hash=stage4_hash,
            final_winner_hash="",
            stages_run=("stage1", "stage2", "stage3", "stage4"),
            failed_at_stage="stage4",
        )
