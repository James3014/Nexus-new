"""Unit tests for MEMORY-EVAL-10 outcome candidate selection."""
import json
from pathlib import Path

ARTIFACT_ROOT = Path(
    "artifacts/runtime/memory_eval_10_outcome_candidate_selection_v0"
)
SELECTED_CANDIDATES_PATH = ARTIFACT_ROOT / "selected_candidates.json"
REJECTED_CANDIDATES_PATH = ARTIFACT_ROOT / "rejected_candidates.json"
VALIDATION_PATH = ARTIFACT_ROOT / "validation.json"
CANDIDATE_POOL_PATH = ARTIFACT_ROOT / "candidate_pool_manifest.json"
CRITERIA_PATH = ARTIFACT_ROOT / "candidate_selection_criteria.json"
MEMORY_MATRIX_PATH = ARTIFACT_ROOT / "memory_availability_matrix.json"


def test_selected_candidates_file_exists():
    assert SELECTED_CANDIDATES_PATH.exists(), (
        f"selected_candidates.json not found at {SELECTED_CANDIDATES_PATH}"
    )


def test_selected_candidates_no_eval_stub_ids():
    data = json.loads(SELECTED_CANDIDATES_PATH.read_text())
    candidates = data.get("selected_candidates", [])
    assert len(candidates) >= 1, "Must have at least 1 selected candidate"
    for c in candidates:
        card_ids = c.get("primary_selected_id", "") or ""
        # Eval stub IDs are synthetic patterns like "eval_stub_*" or "stub_*"
        assert not str(card_ids).startswith("eval_stub"), (
            f"Eval stub ID found in candidate {c['task_id']}: {card_ids}"
        )
        assert not str(card_ids).startswith("stub_"), (
            f"Stub ID found in candidate {c['task_id']}: {card_ids}"
        )


def test_selected_candidates_have_evidence_paths():
    data = json.loads(SELECTED_CANDIDATES_PATH.read_text())
    candidates = data.get("selected_candidates", [])
    for c in candidates:
        evidence = c.get("evidence_paths", [])
        assert len(evidence) >= 1, (
            f"Candidate {c['task_id']} has no evidence_paths"
        )


def test_selection_criteria_exists():
    assert CRITERIA_PATH.exists(), (
        f"candidate_selection_criteria.json not found at {CRITERIA_PATH}"
    )
    data = json.loads(CRITERIA_PATH.read_text())
    assert "scoring_rules" in data, "scoring_rules missing from criteria"
    assert len(data["scoring_rules"]) >= 1, "No scoring rules defined"


def test_selected_candidate_count_matches():
    data = json.loads(SELECTED_CANDIDATES_PATH.read_text())
    candidates = data.get("selected_candidates", [])
    reported_count = data.get("selected_candidate_count", -1)
    assert len(candidates) == reported_count, (
        f"selected_candidate_count {reported_count} != actual count {len(candidates)}"
    )


def test_validation_prohibits_uplift_public_product_training_claims():
    data = json.loads(VALIDATION_PATH.read_text())
    assert data.get("outcome_uplift_observed") is False, (
        "outcome_uplift_observed must be False at selection stage"
    )
    assert data.get("public_claim_allowed") is False, (
        "public_claim_allowed must be False"
    )
    assert data.get("production_ready") is False, (
        "production_ready must be False"
    )
    assert data.get("training_export_allowed") is False, (
        "training_export_allowed must be False"
    )
    assert data.get("real_model_call_executed") is False, (
        "real_model_call_executed must be False at selection stage"
    )


def test_validation_status_correct():
    data = json.loads(VALIDATION_PATH.read_text())
    expected = "MEMORY_EVAL_10_OUTCOME_CANDIDATE_SELECTION_COMPLETE"
    actual = data.get("validation_status")
    assert actual == expected, (
        f"validation_status expected '{expected}', got '{actual}'"
    )


def test_validation_pool_size_positive():
    data = json.loads(VALIDATION_PATH.read_text())
    pool_size = data.get("candidate_pool_size", 0)
    assert pool_size > 0, f"candidate_pool_size must be > 0, got {pool_size}"


def test_memory_availability_matrix_exists():
    assert MEMORY_MATRIX_PATH.exists(), (
        f"memory_availability_matrix.json not found at {MEMORY_MATRIX_PATH}"
    )


def test_c12481_excluded_from_selected():
    data = json.loads(SELECTED_CANDIDATES_PATH.read_text())
    selected_ids = [c["task_id"] for c in data.get("selected_candidates", [])]
    assert "C_12481" not in selected_ids, (
        "C_12481 must not be selected — already tested in MEMORY-EVAL-9 "
        "without new retrieval strategy"
    )


def test_rejected_candidates_file_exists():
    assert REJECTED_CANDIDATES_PATH.exists(), (
        f"rejected_candidates.json not found at {REJECTED_CANDIDATES_PATH}"
    )
