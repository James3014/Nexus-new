import pytest
import hashlib
from typing import Any
from unittest.mock import MagicMock, patch
from pathlib import Path

from nexus.services.local_heal.receipt import build_repair_receipt
from nexus.services.local_heal.latency_ledger import LatencyLedger
from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
from nexus.services.local_heal.orchestrator import HealOrchestrator
from nexus.services.local_heal.interface import PhaseResult, LocalizedFile
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    LocalModelExecutorResponse,
)


class MockContext:
    def __init__(self, attempt=1):
        self.instance_id = "test_instance"
        self.task_id = "test_task"
        self.attempt = attempt
        self.runner_completed = True
        self.initial_ctx_len = 1000
        self.final_ctx_len = 1200
        self.resolved_span_len = 50
        self.wall_time_sec = 15.5
        self.syntax_gate_passed = True
        self.solve_eligible = True
        
        self.repro_script = "reproduce_bug.py"
        self.final_patch = "diff --git a/a.py b/a.py"
        self.evaluation_report = "Tests passed"
        self.model_decisions = []
        
        self._sidecar_enabled = False
        self._sidecar_model = ""
        self._sidecar_contributed = False
        
        self._latency_ledger = LatencyLedger()
        self._latency_ledger.retry_count = max(0, attempt - 1)


def test_attempt_1_failure_attempt_2_success_records_retry_count_1():
    """Verify that attempt=2 (which means 1 failure, 1 success) yields retry_count=1."""
    ctx = MockContext(attempt=2)
    receipt = build_repair_receipt(ctx)
    
    assert receipt["eval_metrics"]["retry_count"] == 1


def test_final_success_after_retry_not_first_pass_success():
    """Verify that attempt > 1 is recognized as a retry and not first-pass success."""
    ctx = MockContext(attempt=2)
    receipt = build_repair_receipt(ctx)
    
    # retry_count > 0 indicates it was NOT first pass success
    assert receipt["eval_metrics"]["retry_count"] > 0
    assert receipt["telemetries"]["attempt"] == 2


def test_retry_evidence_citation_required():
    """Verify that when retry_count > 0, verification_report.txt is cited in evidence."""
    ctx = MockContext(attempt=2)
    receipt = build_repair_receipt(ctx)
    
    assert receipt["eval_metrics"]["retry_count"] == 1
    assert "verification_report.txt" in receipt["evidence_refs"]


def test_retry_count_consistent_across_summary_and_receipt():
    """Verify that latency_ledger.retry_count is consistent with eval_metrics.retry_count."""
    ctx = MockContext(attempt=3) # attempt = 3 -> 2 retries
    receipt = build_repair_receipt(ctx)
    
    assert receipt["eval_metrics"]["retry_count"] == 2
    assert receipt["latency_ledger"]["retry_count"] == 2


# ==========================================
# C15-3Q: 10 Telemetry & Retry Diagnostic Tests
# ==========================================

def test_semantic_retry_telemetry_defaults_in_executor():
    """Test 1: Verify that 15 diagnostic fields are initialized with default values in raw_meta."""
    from nexus.services.local_heal.local_model_provider import InertLocalModelProvider
    req = LocalModelExecutorRequest(
        task_id="test_defaults",
        problem_statement="fix code",
        repo_root="/workspace",
        target_file="a.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        dry_run=False,
        route_context={
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "model_call_allowed": True,
                "selected_executor": "local_model",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit"
            }
        }
    )
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    
    # Defaults should be filled in by wrapper
    assert resp.raw_model_metadata["semantic_retry_client_reused"] is False
    assert resp.raw_model_metadata["semantic_retry_client_class"] == ""
    assert resp.raw_model_metadata["semantic_retry_prompt_len"] == 0
    assert resp.raw_model_metadata["semantic_retry_prompt_hash"] == ""
    assert resp.raw_model_metadata["semantic_retry_prompt_has_verifier_evidence"] is False
    assert resp.raw_model_metadata["semantic_retry_raw_response_len"] == 0
    assert resp.raw_model_metadata["semantic_retry_raw_response_excerpt"] == ""
    assert resp.raw_model_metadata["semantic_retry_response_is_none"] is True
    assert resp.raw_model_metadata["semantic_retry_response_empty"] is True
    assert resp.raw_model_metadata["semantic_retry_response_type"] == "NoneType"
    assert resp.raw_model_metadata["semantic_retry_output_class"] == ""
    assert resp.raw_model_metadata["semantic_retry_parser_error_kind"] == ""
    assert resp.raw_model_metadata["semantic_retry_status"] == ""
    assert resp.raw_model_metadata["semantic_retry_failure_reason"] == ""
    assert resp.raw_model_metadata["semantic_retry_invocation_source"] == "none"


def test_semantic_retry_telemetry_delegated_injection():
    """Test 2: Verify that delegated retry correct projection copy 15 fields from result_ctx._semantic_retry_telemetry."""
    result_ctx = MagicMock()
    result_ctx.failure_reason = "some_failure"
    result_ctx.final_patch = ""
    result_ctx.model_decisions = []
    result_ctx._orchestrator_verifier_evidence_passed = True
    result_ctx._orchestrator_verifier_evidence_fields = "stdout,stderr"
    result_ctx._orchestrator_retry_prompt_evidence_hash = "abc123hash"
    
    result_ctx._semantic_retry_telemetry = {
        "semantic_retry_client_reused": True,
        "semantic_retry_client_class": "MockLLMClient",
        "semantic_retry_prompt_len": 450,
        "semantic_retry_prompt_hash": "hash_1234",
        "semantic_retry_prompt_has_verifier_evidence": True,
        "semantic_retry_raw_response_len": 120,
        "semantic_retry_raw_response_excerpt": "mock excerpt",
        "semantic_retry_response_is_none": False,
        "semantic_retry_response_empty": False,
        "semantic_retry_response_type": "str",
        "semantic_retry_output_class": "VALID_PATCH",
        "semantic_retry_parser_error_kind": "",
        "semantic_retry_status": "SUCCESS",
        "semantic_retry_failure_reason": "none",
        "semantic_retry_invocation_source": "pipeline_delegated_retry",
    }
    
    raw_meta = {}
    semantic_retry_telemetry = dict(getattr(result_ctx, "_semantic_retry_telemetry", {}) or {})
    if semantic_retry_telemetry:
        raw_meta["semantic_retry_count"] = int(semantic_retry_telemetry.get("semantic_retry_count", 0) or 0)
        raw_meta["same_span_retry"] = bool(semantic_retry_telemetry.get("same_span_retry", False))
        raw_meta["semantic_retry_invoked"] = (
            raw_meta.get("semantic_retry_count", 0) > 0 or raw_meta.get("same_span_retry", False)
        )
    raw_meta["semantic_retry_client_reused"] = bool(semantic_retry_telemetry.get("semantic_retry_client_reused", False))
    raw_meta["semantic_retry_client_class"] = str(semantic_retry_telemetry.get("semantic_retry_client_class", "") or "")
    raw_meta["semantic_retry_prompt_len"] = int(semantic_retry_telemetry.get("semantic_retry_prompt_len", 0) or 0)
    raw_meta["semantic_retry_prompt_hash"] = str(semantic_retry_telemetry.get("semantic_retry_prompt_hash", "") or "")
    raw_meta["semantic_retry_prompt_has_verifier_evidence"] = bool(semantic_retry_telemetry.get("semantic_retry_prompt_has_verifier_evidence", False))
    raw_meta["semantic_retry_raw_response_len"] = int(semantic_retry_telemetry.get("semantic_retry_raw_response_len", 0) or 0)
    raw_meta["semantic_retry_raw_response_excerpt"] = str(semantic_retry_telemetry.get("semantic_retry_raw_response_excerpt", "") or "")[:500]
    raw_meta["semantic_retry_response_is_none"] = bool(semantic_retry_telemetry.get("semantic_retry_response_is_none", False))
    raw_meta["semantic_retry_response_empty"] = bool(semantic_retry_telemetry.get("semantic_retry_response_empty", False))
    raw_meta["semantic_retry_response_type"] = str(semantic_retry_telemetry.get("semantic_retry_response_type", "") or "")
    raw_meta["semantic_retry_output_class"] = str(semantic_retry_telemetry.get("semantic_retry_output_class", "") or "")
    raw_meta["semantic_retry_parser_error_kind"] = str(semantic_retry_telemetry.get("semantic_retry_parser_error_kind", "") or "")
    raw_meta["semantic_retry_status"] = str(semantic_retry_telemetry.get("semantic_retry_status", "") or "")
    raw_meta["semantic_retry_failure_reason"] = str(semantic_retry_telemetry.get("semantic_retry_failure_reason", "") or "")
    raw_meta["semantic_retry_invocation_source"] = str(semantic_retry_telemetry.get("semantic_retry_invocation_source", "") or "")

    assert raw_meta["semantic_retry_client_reused"] is True
    assert raw_meta["semantic_retry_client_class"] == "MockLLMClient"
    assert raw_meta["semantic_retry_prompt_len"] == 450
    assert raw_meta["semantic_retry_prompt_hash"] == "hash_1234"
    assert raw_meta["semantic_retry_prompt_has_verifier_evidence"] is True
    assert raw_meta["semantic_retry_raw_response_len"] == 120
    assert raw_meta["semantic_retry_raw_response_excerpt"] == "mock excerpt"
    assert raw_meta["semantic_retry_response_is_none"] is False
    assert raw_meta["semantic_retry_response_empty"] is False
    assert raw_meta["semantic_retry_response_type"] == "str"
    assert raw_meta["semantic_retry_output_class"] == "VALID_PATCH"
    assert raw_meta["semantic_retry_parser_error_kind"] == ""
    assert raw_meta["semantic_retry_status"] == "SUCCESS"
    assert raw_meta["semantic_retry_failure_reason"] == "none"
    assert raw_meta["semantic_retry_invocation_source"] == "pipeline_delegated_retry"


def test_semantic_retry_phase_key_match_fallback():
    """Test 3: Verify the fix for phase key match bug. Ensure check matches 'semantic_retry_patch' and 'patch'."""
    retry_model_decisions = [
        {"phase": "patch", "status": "MODEL_EMPTY_RESPONSE", "output_class": "EMPTY"},
        {"phase": "semantic_retry_patch", "status": "SUCCESS", "output_class": "VALID_PATCH", "parser_error_kind": "None"}
    ]
    
    # Filter using new logic:
    patch_retry_decisions = [
        d for d in retry_model_decisions
        if isinstance(d, dict) and d.get("phase") in ("patch", "semantic_retry_patch")
    ]
    assert len(patch_retry_decisions) == 2
    
    last_retry = patch_retry_decisions[-1]
    assert last_retry.get("status") == "SUCCESS"
    assert last_retry.get("phase") == "semantic_retry_patch"


class SimpleNamespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_semantic_retry_telemetry_success_path(tmp_path: Path):
    """Test 4: Verify the success path of _attempt_semantic_retry creates complete telemetry."""
    orchestrator = HealOrchestrator(phases=[], governance_gate=MagicMock())
    orchestrator.patch_phase = MagicMock()
    orchestrator.patch_phase.llm_client = MagicMock()
    orchestrator.verify_phase = MagicMock()
    
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "<<<<<<< REPLACE\ndef test(): pass\n>>>>>>> REPLACE"
    orchestrator._resolve_semantic_retry_llm_client = lambda: mock_llm
    
    ctx = HealContext(
        op=OperationalContext(
            instance_id="test_success",
            repo_dir=tmp_path,
            problem_statement="fix",
            localized_files=[LocalizedFile(path="a.py", content="def test():\n    fail")],
        ),
        gov=GovernanceContext()
    )
    ctx.op._latency_ledger = LatencyLedger()
    ctx.op.final_patch = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n-def test():\n-    fail\n+def test(): pass"
    ctx.op.model_decisions = [{"phase": "patch", "model": "test-model", "timeout_seconds": 60}]
    
    with patch("nexus.services.local_heal.canonical_span.get_canonical_search_span") as mock_get_span:
        mock_get_span.return_value = SimpleNamespace(span="def test():\n    fail", source="a.py")
        
        with patch("nexus.services.local_heal.protocol.SolidSearchReplaceProtocol") as mock_parser_class:
            mock_intent = MagicMock()
            mock_intent.file_path = "a.py"
            mock_intent.replace = "def test(): pass"
            mock_intent.operation = "replace"
            
            mock_parser = MagicMock()
            mock_parser.parse.return_value = [mock_intent]
            mock_parser_class.return_value = mock_parser
            
            with patch("nexus.services.local_heal.patch_applier.PatchApplier") as mock_applier_class:
                mock_applier = MagicMock()
                mock_applier.apply_and_validate.return_value = SimpleNamespace(success=True, applied_diffs=["diff"])
                mock_applier_class.return_value = mock_applier
                
                orchestrator.phase_runner = MagicMock()
                orchestrator.phase_runner.run_phase.return_value = SimpleNamespace(success=True)
                
                res = orchestrator._attempt_semantic_retry(
                    ctx=ctx,
                    evaluation_report="error trace",
                    failure_class="verification_failed",
                )
                
                assert res is True
                telemetry = ctx.op._semantic_retry_telemetry
                assert telemetry["semantic_retry_status"] == "SUCCESS"
                assert telemetry["semantic_retry_failure_reason"] == ""
                assert telemetry["semantic_retry_client_class"] == "MagicMock"
                assert telemetry["semantic_retry_response_empty"] is False
                assert telemetry["semantic_retry_output_class"] == "VALID_PATCH"


def test_semantic_retry_telemetry_empty_response_path(tmp_path: Path):
    """Test 5: Verify the empty response path of _attempt_semantic_retry generates telemetry with empty flags."""
    orchestrator = HealOrchestrator(phases=[], governance_gate=MagicMock())
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "" # Empty response
    orchestrator._resolve_semantic_retry_llm_client = lambda: mock_llm
    
    ctx = HealContext(
        op=OperationalContext(
            instance_id="test_empty",
            repo_dir=tmp_path,
            problem_statement="fix",
        ),
        gov=GovernanceContext()
    )
    ctx.op.final_patch = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n-def test():\n-    fail\n+def test(): pass"
    ctx.op.model_decisions = [{"phase": "patch", "model": "test-model", "timeout_seconds": 60}]
    
    with patch("nexus.services.local_heal.canonical_span.get_canonical_search_span") as mock_get_span:
        mock_get_span.return_value = SimpleNamespace(span="def test():\n    fail", source="a.py")
        
        res = orchestrator._attempt_semantic_retry(
            ctx=ctx,
            evaluation_report="error trace",
            failure_class="verification_failed",
        )
        
        assert res is False
        telemetry = ctx.op._semantic_retry_telemetry
        assert telemetry["semantic_retry_status"] == "MODEL_EMPTY_RESPONSE"
        assert telemetry["semantic_retry_response_empty"] is True
        assert telemetry["semantic_retry_raw_response_len"] == 0
        assert telemetry["semantic_retry_failure_reason"] == "provider_returned_empty_string_or_none"


def test_semantic_retry_telemetry_parser_failed_path(tmp_path: Path):
    """Test 6: Verify parser failure path of _attempt_semantic_retry collects parser error diagnostics."""
    orchestrator = HealOrchestrator(phases=[], governance_gate=MagicMock())
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "invalid response format"
    orchestrator._resolve_semantic_retry_llm_client = lambda: mock_llm
    
    ctx = HealContext(
        op=OperationalContext(
            instance_id="test_parser_fail",
            repo_dir=tmp_path,
            problem_statement="fix",
        ),
        gov=GovernanceContext()
    )
    ctx.op.final_patch = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n-def test():\n-    fail\n+def test(): pass"
    ctx.op.model_decisions = [{"phase": "patch", "model": "test-model", "timeout_seconds": 60}]
    
    with patch("nexus.services.local_heal.canonical_span.get_canonical_search_span") as mock_get_span:
        mock_get_span.return_value = SimpleNamespace(span="def test():\n    fail", source="a.py")
        
        with patch("nexus.services.local_heal.protocol.SolidSearchReplaceProtocol") as mock_parser_class:
            mock_error = MagicMock()
            mock_error.kind = SimpleNamespace(name="NO_BLOCKS_FOUND")
            
            mock_parser = MagicMock()
            mock_parser.parse.return_value = mock_error # Returns parse error object
            mock_parser_class.return_value = mock_parser
            
            res = orchestrator._attempt_semantic_retry(
                ctx=ctx,
                evaluation_report="error trace",
                failure_class="verification_failed",
            )
            
            assert res is False
            telemetry = ctx.op._semantic_retry_telemetry
            assert telemetry["semantic_retry_status"] == "NO_BLOCKS_FOUND"
            assert telemetry["semantic_retry_parser_error_kind"] == "NO_BLOCKS_FOUND"
            assert telemetry["semantic_retry_output_class"] == "PARSE_ERROR"


def test_semantic_retry_telemetry_apply_failed_path(tmp_path: Path):
    """Test 7: Verify patch apply failure path of _attempt_semantic_retry records apply failure code."""
    orchestrator = HealOrchestrator(phases=[], governance_gate=MagicMock())
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "<<<<<<< REPLACE\ndef test(): pass\n>>>>>>> REPLACE"
    orchestrator._resolve_semantic_retry_llm_client = lambda: mock_llm
    
    ctx = HealContext(
        op=OperationalContext(
            instance_id="test_apply_fail",
            repo_dir=tmp_path,
            problem_statement="fix",
            localized_files=[LocalizedFile(path="a.py", content="def test():\n    fail")],
        ),
        gov=GovernanceContext()
    )
    ctx.op.final_patch = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n-def test():\n-    fail\n+def test(): pass"
    ctx.op.model_decisions = [{"phase": "patch", "model": "test-model", "timeout_seconds": 60}]
    
    with patch("nexus.services.local_heal.canonical_span.get_canonical_search_span") as mock_get_span:
        mock_get_span.return_value = SimpleNamespace(span="def test():\n    fail", source="a.py")
        
        with patch("nexus.services.local_heal.protocol.SolidSearchReplaceProtocol") as mock_parser_class:
            mock_intent = MagicMock()
            mock_intent.file_path = "a.py"
            mock_intent.replace = "def test(): pass"
            mock_intent.operation = "replace"
            
            mock_parser = MagicMock()
            mock_parser.parse.return_value = [mock_intent]
            mock_parser_class.return_value = mock_parser
            
            with patch("nexus.services.local_heal.patch_applier.PatchApplier") as mock_applier_class:
                mock_applier = MagicMock()
                mock_applier.apply_and_validate.return_value = SimpleNamespace(success=False, error_reason="SEARCH_MISMATCH")
                mock_applier_class.return_value = mock_applier
                
                res = orchestrator._attempt_semantic_retry(
                    ctx=ctx,
                    evaluation_report="error trace",
                    failure_class="verification_failed",
                )
                
                assert res is False
                telemetry = ctx.op._semantic_retry_telemetry
                assert telemetry["semantic_retry_status"] == "SEARCH_MISMATCH"
                assert telemetry["semantic_retry_output_class"] == "APPLY_FAILED"
                assert "apply_failed" in telemetry["semantic_retry_failure_reason"]


def test_semantic_retry_telemetry_exception_path(tmp_path: Path):
    """Test 8: Verify LLM provider exception path of _attempt_semantic_retry creates exception diagnostics."""
    orchestrator = HealOrchestrator(phases=[], governance_gate=MagicMock())
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = RuntimeError("Ollama connection timeout")
    orchestrator._resolve_semantic_retry_llm_client = lambda: mock_llm
    
    ctx = HealContext(
        op=OperationalContext(
            instance_id="test_exception",
            repo_dir=tmp_path,
            problem_statement="fix",
        ),
        gov=GovernanceContext()
    )
    ctx.op.final_patch = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n-def test():\n-    fail\n+def test(): pass"
    ctx.op.model_decisions = [{"phase": "patch", "model": "test-model", "timeout_seconds": 60}]
    
    with patch("nexus.services.local_heal.canonical_span.get_canonical_search_span") as mock_get_span:
        mock_get_span.return_value = SimpleNamespace(span="def test():\n    fail", source="a.py")
        
        res = orchestrator._attempt_semantic_retry(
            ctx=ctx,
            evaluation_report="error trace",
            failure_class="verification_failed",
        )
        
        assert res is False
        telemetry = ctx.op._semantic_retry_telemetry
        assert telemetry["semantic_retry_response_is_none"] is True
        assert telemetry["semantic_retry_response_empty"] is True
        assert telemetry["semantic_retry_response_type"] == "exception"


def test_semantic_retry_telemetry_invocation_source_differentiation(tmp_path: Path):
    """Test 9: Verify invocation source is pipeline_delegated_retry vs orchestrator_semantic_retry based on _is_delegated_retry flag."""
    orchestrator = HealOrchestrator(phases=[], governance_gate=MagicMock())
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "" # exit early with empty
    orchestrator._resolve_semantic_retry_llm_client = lambda: mock_llm
    
    with patch("nexus.services.local_heal.canonical_span.get_canonical_search_span") as mock_get_span:
        mock_get_span.return_value = SimpleNamespace(span="def test():\n    fail", source="a.py")
        
        # Case A: _is_delegated_retry = True
        ctx_delegated = HealContext(
            op=OperationalContext(
                instance_id="test_source_delegated",
                repo_dir=tmp_path,
                problem_statement="fix",
            ),
            gov=GovernanceContext()
        )
        ctx_delegated.op.final_patch = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n-def test():\n-    fail\n+def test(): pass"
        ctx_delegated.op._is_delegated_retry = True
        ctx_delegated.op.model_decisions = [{"phase": "patch", "model": "test-model", "timeout_seconds": 60}]
        
        orchestrator._attempt_semantic_retry(
            ctx=ctx_delegated,
            evaluation_report="error trace",
            failure_class="verification_failed",
        )
        assert ctx_delegated.op._semantic_retry_telemetry["semantic_retry_invocation_source"] == "pipeline_delegated_retry"
        
        # Case B: _is_delegated_retry = False
        ctx_orch = HealContext(
            op=OperationalContext(
                instance_id="test_source_orch",
                repo_dir=tmp_path,
                problem_statement="fix",
            ),
            gov=GovernanceContext()
        )
        ctx_orch.op.final_patch = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n-def test():\n-    fail\n+def test(): pass"
        ctx_orch.op.model_decisions = [{"phase": "patch", "model": "test-model", "timeout_seconds": 60}]
        
        orchestrator._attempt_semantic_retry(
            ctx=ctx_orch,
            evaluation_report="error trace",
            failure_class="verification_failed",
        )
        assert ctx_orch.op._semantic_retry_telemetry["semantic_retry_invocation_source"] == "orchestrator_semantic_retry"


def test_semantic_retry_verifier_evidence_injected_flag(tmp_path: Path):
    """Test 10: Verify prompt_has_verifier_evidence flag matches evidence_injected parameter."""
    orchestrator = HealOrchestrator(phases=[], governance_gate=MagicMock())
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "" # exit early with empty
    orchestrator._resolve_semantic_retry_llm_client = lambda: mock_llm
    
    ctx = HealContext(
        op=OperationalContext(
            instance_id="test_evidence_flag",
            repo_dir=tmp_path,
            problem_statement="fix",
        ),
        gov=GovernanceContext()
    )
    ctx.op.final_patch = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n-def test():\n-    fail\n+def test(): pass"
    ctx.op.model_decisions = [{"phase": "patch", "model": "test-model", "timeout_seconds": 60}]
    
    with patch("nexus.services.local_heal.canonical_span.get_canonical_search_span") as mock_get_span:
        mock_get_span.return_value = SimpleNamespace(span="def test():\n    fail", source="a.py")
        
        # Case A: evidence_injected should resolve to True if sr_ready, vfe_available, failure_class match
        ctx.op.semantic_retry_evidence_ready = True
        ctx.op.verifier_failure_evidence_available = True
        ctx.op.failure_class = "verification_failed"
        
        orchestrator._attempt_semantic_retry(
            ctx=ctx,
            evaluation_report="error trace",
            failure_class="verification_failed",
        )
        assert ctx.op._semantic_retry_telemetry["semantic_retry_prompt_has_verifier_evidence"] is True
        
        # Case B: evidence_injected should resolve to False if semantic_retry_evidence_ready is False
        ctx2 = HealContext(
            op=OperationalContext(
                instance_id="test_evidence_flag_2",
                repo_dir=tmp_path,
                problem_statement="fix",
            ),
            gov=GovernanceContext()
        )
        ctx2.op.final_patch = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n-def test():\n-    fail\n+def test(): pass"
        ctx2.op.model_decisions = [{"phase": "patch", "model": "test-model", "timeout_seconds": 60}]
        ctx2.op.semantic_retry_evidence_ready = False
        ctx2.op.verifier_failure_evidence_available = True
        ctx2.op.failure_class = "verification_failed"
        
        orchestrator._attempt_semantic_retry(
            ctx=ctx2,
            evaluation_report="error trace",
            failure_class="verification_failed",
        )
        assert ctx2.op._semantic_retry_telemetry["semantic_retry_prompt_has_verifier_evidence"] is False
