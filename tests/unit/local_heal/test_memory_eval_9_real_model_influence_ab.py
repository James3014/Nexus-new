"""Tests for MEMORY-EVAL-9 Real Model Influence A/B."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path


def test_memory_eval_9_real_model_influence_ab_verification():
    """Verify MEMORY-EVAL-9 artifacts, validation values, raw output hashes and claim boundary adherence."""
    eval_root = Path("artifacts/runtime/memory_eval_9_real_model_influence_ab_v0")
    
    # 1. Verify files exist
    validation_path = eval_root / "validation.json"
    comparison_path = eval_root / "memory_impact_comparison.json"
    receipt_path = eval_root / "model_call_receipt.json"
    raw_on_path = eval_root / "raw_model_output_memory_on.txt"
    raw_off_path = eval_root / "raw_model_output_memory_off.txt"
    
    assert validation_path.exists(), "validation.json does not exist"
    assert comparison_path.exists(), "memory_impact_comparison.json does not exist"
    assert receipt_path.exists(), "model_call_receipt.json does not exist"
    assert raw_on_path.exists(), "raw_model_output_memory_on.txt does not exist"
    assert raw_off_path.exists(), "raw_model_output_memory_off.txt does not exist"
    
    # Compute actual SHA256 of raw outputs
    raw_on_text = raw_on_path.read_text(encoding="utf-8")
    raw_off_text = raw_off_path.read_text(encoding="utf-8")
    
    actual_raw_on_sha256 = hashlib.sha256(raw_on_text.encode("utf-8")).hexdigest()
    actual_raw_off_sha256 = hashlib.sha256(raw_off_text.encode("utf-8")).hexdigest()
    
    # 2. Parse validation.json and match hashes
    val = json.loads(validation_path.read_text(encoding="utf-8"))
    assert val["eval_id"] == "MEMORY_EVAL_9_REAL_MODEL_INFLUENCE_AB_v0"
    assert val["real_model_call_executed"] is True
    assert val["synthetic_delta_measured"] is False
    assert val["real_model_decision_influence_proven"] is True
    assert val["real_patch_synthesis_influence_proven"] is True
    assert val["outcome_uplift_observed"] is False
    assert val["production_ready"] is False
    assert val["public_claim_allowed"] is False
    assert val["training_export_allowed"] is False
    assert val["internal_only"] is True
    assert val["validation_status"] == "MEMORY_EVAL_9_REAL_MODEL_INFLUENCE_AB_MEASURED"
    
    # Hash alignment check in validation.json
    assert val["raw_model_output_sha256_memory_on"] == actual_raw_on_sha256
    assert val["raw_model_output_sha256_memory_off"] == actual_raw_off_sha256
    assert val["patch_sha256_memory_on"] == actual_raw_on_sha256
    assert val["patch_sha256_memory_off"] == actual_raw_off_sha256
    
    # 3. Parse memory_impact_comparison.json and match values
    comp = json.loads(comparison_path.read_text(encoding="utf-8"))
    assert comp["eval_id"] == "MEMORY_EVAL_9_REAL_MODEL_INFLUENCE_AB_v0"
    assert comp["real_model_call_executed"] is True
    assert comp["synthetic_delta_measured"] is False
    assert comp["outcome_uplift_observed"] is False
    
    task_data = comp["comparison"]["C_12481"]
    assert task_data["memory_on"]["retrieved_count"] == 1
    assert task_data["memory_on"]["primary_selected_id"] == "lh-12481"
    assert task_data["memory_off"]["retrieved_count"] == 0
    assert task_data["memory_on"]["output_hash"] == actual_raw_on_sha256
    assert task_data["memory_off"]["output_hash"] == actual_raw_off_sha256
    
    # Read back prompt manifests to verify consistency with comparison
    run_dir = eval_root / "runs" / "C_12481"
    prompt_manifest_on = json.loads((run_dir / "nexus_memory_on/prompt_manifest.json").read_text(encoding="utf-8"))
    prompt_manifest_off = json.loads((run_dir / "nexus_memory_off/prompt_manifest.json").read_text(encoding="utf-8"))
    
    # Rigorous value consistency checks
    assert task_data["memory_on"]["prompt_length_chars"] == prompt_manifest_on["prompt_length_chars"]
    assert task_data["memory_off"]["prompt_length_chars"] == prompt_manifest_off["prompt_length_chars"]
    
    # 4. Audit all JSON artifacts under C_12481 runs (22 files total)
    assert run_dir.exists()
    required_names = [
        "arm_result.json", "bottleneck_classification.json", "evidence_bundle.json",
        "evidence_packet.json", "input_manifest.json", "memory_trace.json",
        "model_output_summary.json", "patch_apply_result.json", "prompt_manifest.json",
        "receipt.json", "verifier_result.json"
    ]
    
    for arm in ["nexus_memory_on", "nexus_memory_off"]:
        arm_dir = run_dir / arm
        assert arm_dir.exists()
        for name in required_names:
            file_path = arm_dir / name
            assert file_path.exists(), f"{file_path} is missing"
            
            data = json.loads(file_path.read_text(encoding="utf-8"))
            assert data.get("artifact_source") == "live_runtime", f"{file_path} lacks live_runtime source"
            assert data.get("created_during_run") is True, f"{file_path} lacks created_during_run=true"
            
            # Check primary_selected_id hygiene in memory_trace.json
            if name == "memory_trace.json" and arm == "nexus_memory_on":
                assert "primary_selected_id" in data
                assert data["primary_selected_id"] == "lh-12481"
                assert "lh-12481" in data["selected_ids"]
