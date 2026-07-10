from __future__ import annotations

import os

import pytest
from unittest.mock import patch

from nexus.services.local_heal.p3_local_diagnosis_runtime import (
    P3LocalDiagnosisRuntimeReceipt,
    RealLocalDiagnosis,
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


class TestRealLocalDiagnosis:
    def test_ollama_disabled_returns_stub(self) -> None:
        if "NEXUS_OLLAMA_ENABLED" in os.environ:
            del os.environ["NEXUS_OLLAMA_ENABLED"]
        diag = RealLocalDiagnosis()
        skeleton = {"task_id": "t1", "p3_task_difficulty": "medium"}
        anchor = {"target_file": "a.py", "target_symbol": "foo"}
        receipt = diag.compute_p3_local_diagnosis_runtime(skeleton, anchor)
        assert isinstance(receipt, P3LocalDiagnosisRuntimeReceipt)

    def test_ollama_enabled_calls_3b(self) -> None:
        os.environ["NEXUS_OLLAMA_ENABLED"] = "1"
        diag = RealLocalDiagnosis()
        assert diag.ollama_enabled is True
        assert diag.MODEL_NAME == "qwen2.5-s2t-advisor:3b"
        skeleton = {"task_id": "t1", "p3_task_difficulty": "medium"}
        anchor = {"target_file": "a.py", "target_symbol": "foo"}
        receipt = diag.compute_p3_local_diagnosis_runtime(skeleton, anchor)
        assert receipt.cloud_call_invoked is True
        assert receipt.runtime_behavior_changed is True
        del os.environ["NEXUS_OLLAMA_ENABLED"]

    def test_no_real_call_without_env(self) -> None:
        if "NEXUS_OLLAMA_ENABLED" in os.environ:
            del os.environ["NEXUS_OLLAMA_ENABLED"]
        with patch(
            "nexus.services.local_heal.p3_local_diagnosis_runtime.InertLocalModelProvider.generate"
        ) as mock_generate:
            diag = RealLocalDiagnosis()
            diag.compute_p3_local_diagnosis_runtime(
                {"task_id": "t1"}, {"target_file": "a.py"}
            )
            mock_generate.assert_not_called()

    def test_existing_p1b_still_works(self) -> None:
        skeleton = {"task_id": "t1", "p3_task_difficulty": "medium"}
        anchor = {"target_file": "a.py", "target_symbol": "foo"}
        receipt = compute_p3_local_diagnosis_runtime(skeleton, anchor)
        assert isinstance(receipt, P3LocalDiagnosisRuntimeReceipt)

    def test_3b_provider_name(self) -> None:
        os.environ["NEXUS_OLLAMA_ENABLED"] = "1"
        diag = RealLocalDiagnosis()
        assert diag.PROVIDER_NAME == "OllamaLocalModelProvider"
        del os.environ["NEXUS_OLLAMA_ENABLED"]

    # === L3-A: real 3B advisor ===

    def test_real_3b_advisor_ollama_disabled_stub(self) -> None:
        if "NEXUS_OLLAMA_ENABLED" in os.environ:
            del os.environ["NEXUS_OLLAMA_ENABLED"]
        diag = RealLocalDiagnosis()
        skeleton = {"task_id": "t1", "p3_task_difficulty": "medium"}
        anchor = {"target_file": "a.py", "target_symbol": "foo"}
        receipt = diag.compute_p3_local_diagnosis_runtime(skeleton, anchor)
        assert receipt.advisor_recommendation == ""

    def test_real_3b_advisor_ollama_enabled_uses_ollama(self) -> None:
        os.environ["NEXUS_OLLAMA_ENABLED"] = "1"
        diag = RealLocalDiagnosis()
        skeleton = {"task_id": "t1", "p3_task_difficulty": "hard"}
        anchor = {"target_file": "b.py", "target_symbol": "bar"}
        receipt = diag.compute_p3_local_diagnosis_runtime(skeleton, anchor)
        assert isinstance(receipt, P3LocalDiagnosisRuntimeReceipt)
        assert receipt.cloud_call_invoked is True
        del os.environ["NEXUS_OLLAMA_ENABLED"]

    def test_real_3b_advisor_prompt_construction(self) -> None:
        from nexus.services.local_heal.p3_local_diagnosis_runtime import _build_diagnosis_prompt
        skeleton = {
            "task_id": "t1",
            "p3_task_difficulty": "hard",
            "p3_target_file": "src/main.py",
            "p3_target_symbol": "calculate_total",
            "p3_line_span": "42-58",
            "p3_failure_class": "IndexError",
        }
        prompt = _build_diagnosis_prompt(skeleton)
        assert "hard" in prompt
        assert "src/main.py" in prompt
        assert "calculate_total" in prompt
        assert "42-58" in prompt
        assert "IndexError" in prompt

    def test_real_3b_advisor_json_parsing(self) -> None:
        from nexus.services.local_heal.p3_local_diagnosis_runtime import _parse_advisor_response
        raw = '{"advisor_recommendation": "check boundary conditions on line 42"}'
        result = _parse_advisor_response(raw)
        assert result == "check boundary conditions on line 42"

    def test_real_3b_advisor_fallback_on_empty_response(self) -> None:
        from nexus.services.local_heal.p3_local_diagnosis_runtime import _parse_advisor_response
        assert _parse_advisor_response("") == ""
        assert _parse_advisor_response("  ") == ""
        assert _parse_advisor_response("not json") != ""  # fallback truncation
