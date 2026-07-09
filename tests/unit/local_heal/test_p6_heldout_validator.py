"""P6-D4: Heldout Fixture Validator Tests."""
from __future__ import annotations

import json
import os
import tempfile
import pytest
from nexus.services.local_heal.p6_heldout_validator import (
    P6HeldoutValidationResult,
    validate_heldout_fixture,
    validate_heldout_file,
)


def _valid_case(case_id="H01", difficulty="easy", scenario="healthy"):
    return {
        "case_id": case_id, "task_difficulty": difficulty, "quota_scenario": scenario,
        "quota_known": True, "local_available": True,
        "expected_degradation_action": "keep_full_committee",
        "expected_cloud_allowed": True, "expected_local_allowed": True,
        "expected_committee_allowed": True, "expected_p5_allowed": True,
        "expected_candidate_count_min": 3, "expected_candidate_count_max": 10,
        "verifier_required": True, "claim_gate_required": True,
        "public_claim_allowed": False, "default_runtime_allowed": False,
        "production_ready": False, "expected_result_class": "pass", "notes": "test",
    }


def _valid_fixture():
    cases = []
    for i in range(36):
        difficulty = ["easy", "medium", "hard"][i % 3]
        scenario = ["healthy", "constrained", "exhausted_local_available", "exhausted_local_unavailable", "unknown"][i % 5]
        cases.append(_valid_case(f"H{i+1:02d}", difficulty, scenario))
    return cases


def test_valid_fixture_passes():
    """P6-D4: Valid D3 fixture passes."""
    result = validate_heldout_fixture(_valid_fixture())
    assert result.valid is True
    assert result.case_count == 36


def test_fewer_than_30_fails():
    """P6-D4: Fewer than 30 cases fails."""
    cases = [_valid_case(f"H{i}") for i in range(10)]
    result = validate_heldout_fixture(cases)
    assert result.valid is False
    assert "fewer_than_30_cases" in result.blocked_reasons


def test_missing_difficulty_fails():
    """P6-D4: Missing difficulty fails."""
    cases = _valid_fixture()
    cases[0]["task_difficulty"] = "extra"
    result = validate_heldout_fixture(cases)
    assert result.valid is False
    assert "missing_difficulty" in result.blocked_reasons


def test_public_claim_violation_fails():
    """P6-D4: public_claim_allowed=true fails."""
    cases = _valid_fixture()
    cases[0]["public_claim_allowed"] = True
    result = validate_heldout_fixture(cases)
    assert result.valid is False
    assert result.public_claim_allowed_violations == 1


def test_verifier_required_violation_fails():
    """P6-D4: verifier_required=false fails."""
    cases = _valid_fixture()
    cases[0]["verifier_required"] = False
    result = validate_heldout_fixture(cases)
    assert result.valid is False
    assert result.verifier_required_violations == 1


def test_json_serializable():
    """P6-D4: Result is JSON-serializable."""
    result = validate_heldout_fixture(_valid_fixture())
    d = {"valid": result.valid, "case_count": result.case_count}
    json_str = json.dumps(d)
    assert len(json_str) > 0


def test_validate_file():
    """P6-D4: File validation works."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "fixture.json")
        with open(path, "w") as f:
            json.dump(_valid_fixture(), f)
        result = validate_heldout_file(path)
        assert result.valid is True
        assert result.case_count == 36
