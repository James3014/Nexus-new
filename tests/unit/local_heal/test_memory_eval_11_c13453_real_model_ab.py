"""Unit tests for MEMORY-EVAL-11: C_13453 Astropy real model A/B evaluation."""
import json
from pathlib import Path

ARTIFACT_ROOT = Path("artifacts/runtime/memory_eval_11_c13453_real_model_ab_v0")
VALIDATION_PATH = ARTIFACT_ROOT / "validation.json"
RECEIPT_PATH = ARTIFACT_ROOT / "model_call_receipt.json"
COMPARISON_PATH = ARTIFACT_ROOT / "memory_impact_comparison.json"
RAW_ON_PATH = ARTIFACT_ROOT / "raw_model_output_memory_on.txt"
RAW_OFF_PATH = ARTIFACT_ROOT / "raw_model_output_memory_off.txt"
RUNS_ROOT = ARTIFACT_ROOT / "runs" / "C_13453"


def test_validation_file_exists():
    assert VALIDATION_PATH.exists(), f"validation.json not found at {VALIDATION_PATH}"


def test_real_model_call_executed():
    data = json.loads(VALIDATION_PATH.read_text())
    assert data["real_model_call_executed"] is True, (
        "real_model_call_executed must be True"
    )


def test_synthetic_delta_false():
    data = json.loads(VALIDATION_PATH.read_text())
    assert data["synthetic_delta_measured"] is False, (
        "synthetic_delta_measured must be False for a real model call eval"
    )


def test_prohibit_public_claim_and_training_export():
    data = json.loads(VALIDATION_PATH.read_text())
    assert data["public_claim_allowed"] is False, "public_claim_allowed must be False"
    assert data["training_export_allowed"] is False, "training_export_allowed must be False"
    assert data["production_ready"] is False, "production_ready must be False"
    assert data["internal_only"] is True, "internal_only must be True"


def test_prompt_delta_observed():
    """Memory On arm must produce a different (longer) prompt than Memory Off arm."""
    data = json.loads(VALIDATION_PATH.read_text())
    assert data["prompt_delta_observed"] is True, (
        "prompt_delta_observed must be True — memory injection must change prompt length"
    )


def test_model_call_receipt_exists_and_has_hashes():
    assert RECEIPT_PATH.exists(), f"model_call_receipt.json not found at {RECEIPT_PATH}"
    data = json.loads(RECEIPT_PATH.read_text())
    assert "raw_model_output_sha256_on" in data, "Missing sha256 for memory_on output"
    assert "raw_model_output_sha256_off" in data, "Missing sha256 for memory_off output"
    assert len(data["raw_model_output_sha256_on"]) == 64, "SHA256 must be 64 hex chars"
    assert len(data["raw_model_output_sha256_off"]) == 64, "SHA256 must be 64 hex chars"


def test_raw_model_outputs_exist_and_nonempty():
    assert RAW_ON_PATH.exists(), f"raw_model_output_memory_on.txt not found"
    assert RAW_OFF_PATH.exists(), f"raw_model_output_memory_off.txt not found"
    assert len(RAW_ON_PATH.read_text()) > 0, "raw_model_output_memory_on.txt is empty"
    assert len(RAW_OFF_PATH.read_text()) > 0, "raw_model_output_memory_off.txt is empty"


def test_raw_output_sha256_matches_receipt():
    """Verify that the SHA256 in receipt matches the actual file content."""
    import hashlib
    data = json.loads(RECEIPT_PATH.read_text())
    on_text = RAW_ON_PATH.read_text(encoding="utf-8")
    off_text = RAW_OFF_PATH.read_text(encoding="utf-8")
    computed_on = hashlib.sha256(on_text.encode("utf-8")).hexdigest()
    computed_off = hashlib.sha256(off_text.encode("utf-8")).hexdigest()
    assert computed_on == data["raw_model_output_sha256_on"], (
        f"SHA256 mismatch for memory_on: computed={computed_on}, receipt={data['raw_model_output_sha256_on']}"
    )
    assert computed_off == data["raw_model_output_sha256_off"], (
        f"SHA256 mismatch for memory_off: computed={computed_off}, receipt={data['raw_model_output_sha256_off']}"
    )


def test_both_arm_artifact_directories_exist():
    on_dir = RUNS_ROOT / "nexus_memory_on"
    off_dir = RUNS_ROOT / "nexus_memory_off"
    assert on_dir.exists(), f"nexus_memory_on directory missing at {on_dir}"
    assert off_dir.exists(), f"nexus_memory_off directory missing at {off_dir}"


def test_per_arm_artifacts_complete():
    required = [
        "verifier_result.json",
        "memory_trace.json",
        "prompt_manifest.json",
        "receipt.json",
        "arm_result.json",
    ]
    for arm in ["nexus_memory_on", "nexus_memory_off"]:
        arm_dir = RUNS_ROOT / arm
        for fname in required:
            path = arm_dir / fname
            assert path.exists(), f"Missing {fname} in {arm}"


def test_memory_on_arm_retrieved_at_least_one_lesson():
    data = json.loads(RECEIPT_PATH.read_text())
    lessons = data.get("memory_on_lessons_retrieved", 0)
    assert lessons >= 1, (
        f"Memory On arm must retrieve >= 1 lesson. Got {lessons}. "
        "C_13453 has 13 memory episodes in the store."
    )


def test_comparison_file_aligns_with_artifacts():
    data = json.loads(COMPARISON_PATH.read_text())
    assert data["artifact_source"] == "live_runtime", (
        "memory_impact_comparison must be live_runtime"
    )
    assert data["created_during_run"] is True, (
        "created_during_run must be True"
    )
    assert data["data_aligned_to_live_artifacts"] is True, (
        "data_aligned_to_live_artifacts must be True"
    )
    # Memory off must show 0 lessons
    assert data["nexus_memory_off"]["lessons_retrieved"] == 0, (
        "memory_off arm must retrieve 0 lessons"
    )
