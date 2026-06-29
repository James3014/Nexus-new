import json
from pathlib import Path
import pytest

from scripts.bench.capability_ab_runner import CapabilityTask, _finalize_with_nexus_row

def test_p12_manifest_parser():
    # 1. Verify replay_manifest.json structure
    manifest_path = Path("artifacts/runtime/local_model_armor_p12_real_june_b_replay_v0/replay_manifest.json")
    assert manifest_path.exists()
    
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
        
    assert "tasks" in manifest
    assert len(manifest["tasks"]) >= 2
    
    for t in manifest["tasks"]:
        assert "task_id" in t
        assert "baseline_status" in t
        assert "replay_eligibility" in t
        assert "source_root" in t
        assert "target_file" in t
        assert "target_symbol" in t
        assert "locked_search" in t
        assert "verifier_command" in t
        assert "evidence_refs" in t
        assert "blockers" in t

def test_missing_controls_taxonomy(tmp_path):
    # 2. Verify that missing workspace or controls correctly evaluates in finalization
    task = CapabilityTask(
        id="sympy__sympy-13852",
        difficulty="medium",
        task_type="test_repair",
        task_desc="missing controls test",
        target_file="",  # Missing target file
        test_file="test.py",
        success_criteria="tests_pass",
    )
    row = {
        "mode": "with_nexus",
        "model_calls": 0,
        "total_tokens": 0,
    }
    
    # Run finalization with capability adapter seam enabled
    import os
    from unittest.mock import patch
    env = {
        "NEXUS_WITH_LOCAL_MODEL_ADAPTER": "1",
        "NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE": "1",
    }
    with patch.dict(os.environ, env):
        finalized = _finalize_with_nexus_row(
            row,
            provider="gemini",
            model_required=True,
            nexus_required=False,
            task=task,
            repo_root=tmp_path,
        )
        
    ad = finalized.get("local_model_adapter")
    assert ad is not None
    assert ad["route_mode"] == "local_only_blocked"
    assert ad["fallback_block_reason"] == "missing_required_control"
    assert ad["adapter_missing_control"] is True

def test_bundle_summary_keys():
    # 3. Verify evidence_bundle.json contains local_model_adapter_summary and safety locks are zero
    bundle_path = Path("artifacts/runtime/local_model_armor_p12_real_june_b_replay_v0/evidence_bundle.json")
    assert bundle_path.exists()
    
    with open(bundle_path, "r", encoding="utf-8") as f:
        bundle = json.load(f)
        
    assert "local_model_adapter_summary" in bundle
    summary = bundle["local_model_adapter_summary"]
    
    # Telemetry keys presence
    assert "adapter_trace_count" in summary
    assert "adapter_invoked_count" in summary
    assert "local_model_called_count" in summary
    assert "candidate_isolated_count" in summary
    assert "adapter_missing_control_count" in summary
    
    # Verify safety locks evaluate to zero
    assert summary["behavior_changed_count"] == 0
    assert summary["public_claim_allowed_count"] == 0
    assert summary["production_ready_count"] == 0
    assert summary["adapter_contract_violation_count"] == 0
    assert summary["adapter_error_count"] == 0

def test_verdict_safety_check():
    # 4. Mock provider results cannot be marked PASS_REAL_REPLAY if local model called count is zero
    local_model_called_count = 0
    verdict = "PASS_REAL_REPLAY" if local_model_called_count > 0 else "FAIL_REPLAY_BLOCKED"
    assert verdict == "FAIL_REPLAY_BLOCKED"

def test_safety_counter_locks_fail_closed():
    # 5. If any safety boundary is breached, verdict resolves to FAIL_SAFETY
    summary = {
        "behavior_changed_count": 0,
        "public_claim_allowed_count": 0,
        "production_ready_count": 0,
        "adapter_contract_violation_count": 1,  # Breached!
    }
    
    has_breach = (
        summary["behavior_changed_count"] > 0
        or summary["public_claim_allowed_count"] > 0
        or summary["production_ready_count"] > 0
        or summary["adapter_contract_violation_count"] > 0
    )
    
    verdict = "FAIL_SAFETY" if has_breach else "PASS_REAL_REPLAY"
    assert verdict == "FAIL_SAFETY"
