from __future__ import annotations

import pytest
from unittest.mock import patch

from nexus.services.local_heal.four_stage_orchestrator import (
    FourStageOrchestrator,
    FourStageReceipt,
)


@pytest.fixture
def orchestrator() -> FourStageOrchestrator:
    return FourStageOrchestrator()


@pytest.fixture
def anchor() -> dict:
    return {"target_file": "a.py", "difficulty": "medium"}


def _make_receipt(**overrides: dict) -> object:
    defaults = {
        "enabled": True,
        "authority": "runtime_enabled",
        "task_id": "t1",
        "task_difficulty": "medium",
        "target_file": "a.py",
        "target_symbol": "foo",
        "line_span": "1-10",
        "old_block_hash": "abc",
        "failure_class": "test",
        "failure_summary": "test failure",
        "verifier_summary": "verifier_summary",
        "anchor_status": "available",
        "hash_chain_status": "complete",
        "compact_prompt": "fix the bug",
        "compact_prompt_hash": "hash1",
        "compact_prompt_token_estimate": 50,
        "source_context_included": True,
        "cloud_ready": True,
        "claim_eligible": True,
        "public_claim_allowed": False,
        "reason": "runtime_test",
        "cloud_call_invoked": True,
        "runtime_behavior_changed": True,
    }
    defaults.update(overrides)
    return type("FakeReceipt", (), defaults)()


class TestFourStageOrchestratorStage3Pass:
    def test_stage3_pass_no_stage4(self, orchestrator: FourStageOrchestrator, anchor: dict) -> None:
        with (
            patch.object(orchestrator.diagnosis, "compute_p3_local_diagnosis_runtime") as mock_diag,
            patch.object(orchestrator.cloud_executor, "run_with_compact_prompt") as mock_cloud,
            patch.object(orchestrator.cheap_verifier, "compute_p3_cheap_verifier_runtime") as mock_verify,
        ):
            mock_diag.return_value = _make_receipt(compact_prompt_hash="h1")
            mock_cloud.return_value = type("FakeCloud", (), {
                "raw_output": "cloud_candidate",
                "raw_output_hash": "h2",
                "invoked": True,
                "model_name": "mock",
                "error": "",
                "latency_ms": 0,
            })()
            mock_verify.return_value = _make_receipt(
                cheap_verifier_result="runtime_invoked",
            )

            receipt = orchestrator.run_four_stage(
                task_id="t1",
                problem_statement="fix bug",
                anchor=anchor,
            )

            assert isinstance(receipt, FourStageReceipt)
            assert receipt.task_id == "t1"
            assert receipt.stage3_verifier_result == "pass"
            assert receipt.final_winner_hash == "h2"
            assert receipt.stages_run == ("stage1", "stage2", "stage3")
            assert receipt.failed_at_stage == ""


class TestFourStageOrchestratorStage3FailStage4Pass:
    def test_stage3_fail_stage4_pass(self, orchestrator: FourStageOrchestrator, anchor: dict) -> None:
        with (
            patch.object(orchestrator.diagnosis, "compute_p3_local_diagnosis_runtime") as mock_diag,
            patch.object(orchestrator.cloud_executor, "run_with_compact_prompt") as mock_cloud,
            patch.object(orchestrator.cheap_verifier, "compute_p3_cheap_verifier_runtime") as mock_verify,
            patch.object(orchestrator.retry, "compute_p3_retry_stub_runtime") as mock_retry,
        ):
            mock_diag.return_value = _make_receipt(compact_prompt_hash="h1")
            mock_cloud.return_value = type("FakeCloud", (), {
                "raw_output": "cloud_candidate", "raw_output_hash": "h2", "invoked": True,
                "model_name": "mock", "error": "", "latency_ms": 0,
            })()
            mock_verify.return_value = _make_receipt(
                cheap_verifier_result="not_run_shadow_only",
            )
            mock_retry.return_value = _make_receipt(
                retry_candidate_generated=True,
                retry_candidate_hash="h4",
            )

            receipt = orchestrator.run_four_stage(
                task_id="t1",
                problem_statement="fix bug",
                anchor=anchor,
            )

            assert isinstance(receipt, FourStageReceipt)
            assert receipt.stage3_verifier_result == "fail"
            assert receipt.stage4_retry_hash == "h4"
            assert receipt.final_winner_hash == "h4"
            assert receipt.stages_run == ("stage1", "stage2", "stage3", "stage4")
            assert receipt.failed_at_stage == ""


class TestFourStageOrchestratorAllFail:
    def test_all_stages_fail(self, orchestrator: FourStageOrchestrator, anchor: dict) -> None:
        with (
            patch.object(orchestrator.diagnosis, "compute_p3_local_diagnosis_runtime") as mock_diag,
            patch.object(orchestrator.cloud_executor, "run_with_compact_prompt") as mock_cloud,
            patch.object(orchestrator.cheap_verifier, "compute_p3_cheap_verifier_runtime") as mock_verify,
            patch.object(orchestrator.retry, "compute_p3_retry_stub_runtime") as mock_retry,
        ):
            mock_diag.return_value = _make_receipt(compact_prompt_hash="h1")
            mock_cloud.return_value = type("FakeCloud", (), {
                "raw_output": "cloud_candidate", "raw_output_hash": "h2", "invoked": True,
                "model_name": "mock", "error": "", "latency_ms": 0,
            })()
            mock_verify.return_value = _make_receipt(
                cheap_verifier_result="not_run_shadow_only",
            )
            mock_retry.return_value = _make_receipt(
                retry_candidate_generated=False,
                retry_candidate_hash="",
            )

            receipt = orchestrator.run_four_stage(
                task_id="t1",
                problem_statement="fix bug",
                anchor=anchor,
            )

            assert isinstance(receipt, FourStageReceipt)
            assert receipt.final_winner_hash == ""
            assert receipt.failed_at_stage == "stage4"


class TestFourStageOrchestratorSequence:
    def test_stages_run_sequence(self, orchestrator: FourStageOrchestrator, anchor: dict) -> None:
        with (
            patch.object(orchestrator.diagnosis, "compute_p3_local_diagnosis_runtime") as mock_diag,
            patch.object(orchestrator.cloud_executor, "run_with_compact_prompt") as mock_cloud,
            patch.object(orchestrator.cheap_verifier, "compute_p3_cheap_verifier_runtime") as mock_verify,
        ):
            mock_diag.return_value = _make_receipt(compact_prompt_hash="h1")
            mock_cloud.return_value = type("FakeCloud", (), {
                "raw_output": "cloud_candidate", "raw_output_hash": "h2", "invoked": True,
                "model_name": "mock", "error": "", "latency_ms": 0,
            })()
            mock_verify.return_value = _make_receipt(
                cheap_verifier_result="runtime_invoked",
            )

            receipt = orchestrator.run_four_stage(
                task_id="t1",
                problem_statement="fix bug",
                anchor=anchor,
            )

            mock_diag.assert_called_once()
            mock_cloud.assert_called_once()
            mock_verify.assert_called_once()

    def test_failed_at_stage_field(self, orchestrator: FourStageOrchestrator, anchor: dict) -> None:
        with (
            patch.object(orchestrator.diagnosis, "compute_p3_local_diagnosis_runtime") as mock_diag,
            patch.object(orchestrator.cloud_executor, "run_with_compact_prompt") as mock_cloud,
            patch.object(orchestrator.cheap_verifier, "compute_p3_cheap_verifier_runtime") as mock_verify,
            patch.object(orchestrator.retry, "compute_p3_retry_stub_runtime") as mock_retry,
        ):
            mock_diag.return_value = _make_receipt(compact_prompt_hash="h1")
            mock_cloud.return_value = type("FakeCloud", (), {
                "raw_output": "cloud_candidate", "raw_output_hash": "h2", "invoked": True,
                "model_name": "mock", "error": "", "latency_ms": 0,
            })()
            mock_verify.return_value = _make_receipt(
                cheap_verifier_result="not_run_shadow_only",
            )
            mock_retry.return_value = _make_receipt(
                retry_candidate_generated=False,
                retry_candidate_hash="",
            )

            receipt = orchestrator.run_four_stage(
                task_id="t1",
                problem_statement="fix bug",
                anchor=anchor,
            )

            assert receipt.failed_at_stage == "stage4"

    def test_final_winner_hash_stage3(self, orchestrator: FourStageOrchestrator, anchor: dict) -> None:
        with (
            patch.object(orchestrator.diagnosis, "compute_p3_local_diagnosis_runtime") as mock_diag,
            patch.object(orchestrator.cloud_executor, "run_with_compact_prompt") as mock_cloud,
            patch.object(orchestrator.cheap_verifier, "compute_p3_cheap_verifier_runtime") as mock_verify,
        ):
            mock_diag.return_value = _make_receipt(compact_prompt_hash="h1")
            mock_cloud.return_value = type("FakeCloud", (), {
                "raw_output": "cloud_candidate", "raw_output_hash": "h2", "invoked": True,
                "model_name": "mock", "error": "", "latency_ms": 0,
            })()
            mock_verify.return_value = _make_receipt(
                cheap_verifier_result="runtime_invoked",
            )

            receipt = orchestrator.run_four_stage(
                task_id="t1",
                problem_statement="fix bug",
                anchor=anchor,
            )

            assert receipt.final_winner_hash == "h2"

    def test_final_winner_hash_stage4(self, orchestrator: FourStageOrchestrator, anchor: dict) -> None:
        with (
            patch.object(orchestrator.diagnosis, "compute_p3_local_diagnosis_runtime") as mock_diag,
            patch.object(orchestrator.cloud_executor, "run_with_compact_prompt") as mock_cloud,
            patch.object(orchestrator.cheap_verifier, "compute_p3_cheap_verifier_runtime") as mock_verify,
            patch.object(orchestrator.retry, "compute_p3_retry_stub_runtime") as mock_retry,
        ):
            mock_diag.return_value = _make_receipt(compact_prompt_hash="h1")
            mock_cloud.return_value = type("FakeCloud", (), {
                "raw_output": "cloud_candidate", "raw_output_hash": "h2", "invoked": True,
                "model_name": "mock", "error": "", "latency_ms": 0,
            })()
            mock_verify.return_value = _make_receipt(
                cheap_verifier_result="not_run_shadow_only",
            )
            mock_retry.return_value = _make_receipt(
                retry_candidate_generated=True,
                retry_candidate_hash="h4",
            )

            receipt = orchestrator.run_four_stage(
                task_id="t1",
                problem_statement="fix bug",
                anchor=anchor,
            )

            assert receipt.final_winner_hash == "h4"

    def test_receipt_frozen(self) -> None:
        r = FourStageReceipt(
            task_id="t1",
            stage1_diagnosis_hash="",
            stage2_candidate_hash="",
            stage3_verifier_result="",
            stage4_retry_hash="",
            final_winner_hash="",
            stages_run=(),
            failed_at_stage="",
        )
        with pytest.raises(AttributeError):
            r.task_id = "t2"
