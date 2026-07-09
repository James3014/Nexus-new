from __future__ import annotations

import pytest
from unittest.mock import patch

from nexus.services.local_heal.p3_local_diagnosis_runtime import (
    P3LocalDiagnosisRuntimeReceipt,
    compute_p3_local_diagnosis_runtime,
)


def test_p3_local_diagnosis_runtime_twin_exists() -> None:
    import nexus.services.local_heal.p3_local_diagnosis_runtime  # noqa: F401


def test_compute_p3_local_diagnosis_runtime_returns_receipt() -> None:
    skeleton = {"task_id": "t1", "p3_task_difficulty": "medium"}
    anchor = {"target_file": "a.py", "target_symbol": "foo"}
    receipt = compute_p3_local_diagnosis_runtime(skeleton, anchor)
    assert isinstance(receipt, P3LocalDiagnosisRuntimeReceipt)


def test_p3_local_diagnosis_runtime_cloud_call_invoked_true() -> None:
    skeleton = {"task_id": "t1"}
    anchor = {"target_file": "a.py"}
    receipt = compute_p3_local_diagnosis_runtime(skeleton, anchor)
    assert receipt.cloud_call_invoked is True


def test_p3_local_diagnosis_runtime_behavior_changed_true() -> None:
    skeleton = {"task_id": "t1"}
    anchor = {"target_file": "a.py"}
    receipt = compute_p3_local_diagnosis_runtime(skeleton, anchor)
    assert receipt.runtime_behavior_changed is True


def test_p3_local_diagnosis_runtime_no_real_model_call() -> None:
    skeleton = {"task_id": "t1"}
    anchor = {"target_file": "a.py"}
    with patch("nexus.services.local_heal.p3_local_diagnosis_runtime.compute_p3_local_diagnosis") as mock_diag:
        mock_diag.return_value = type("FakeDiag", (), {
            "enabled": True, "authority": "shadow_only", "task_id": "t1",
            "task_difficulty": "medium", "target_file": "a.py",
            "target_symbol": "", "line_span": "", "old_block_hash": "",
            "failure_class": "", "failure_summary": "", "verifier_summary": "",
            "anchor_status": "available", "hash_chain_status": "incomplete",
            "compact_prompt": "test", "compact_prompt_hash": "abc",
            "compact_prompt_token_estimate": 1, "source_context_included": True,
            "cloud_ready": False, "cloud_call_invoked": False,
            "runtime_behavior_changed": False, "claim_eligible": False,
            "public_claim_allowed": False, "reason": "test",
        })()
        receipt = compute_p3_local_diagnosis_runtime(skeleton, anchor)
        mock_diag.assert_called_once()
        assert receipt.cloud_call_invoked is True
