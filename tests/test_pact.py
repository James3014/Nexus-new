"""Tests for PACT schema validation and dual-output."""
import pytest
from nexus.contracts.pact import PACTRecord, validate_pact_record, pact_from_advisor_output


def test_pact_record_creation():
    """PACT record can be created with required fields."""
    record = PACTRecord(
        task_id="test-001",
        route_risk_tier="low",
        candidate_ids=["A", "B"],
        recommended_candidate_id="A",
    )
    assert record.task_id == "test-001"
    assert record.route_risk_tier == "low"
    assert record.observation_only is True


def test_pact_record_to_dict():
    """PACT record serializes to dict correctly."""
    record = PACTRecord(
        task_id="test-002",
        route_risk_tier="medium",
        candidate_ids=["X"],
        recommended_candidate_id="X",
        selection_reason_codes=["high_score"],
    )
    d = record.to_dict()
    assert d["task_id"] == "test-002"
    assert d["route_risk_tier"] == "medium"
    assert "high_score" in d["selection_reason_codes"]
    assert d["observation_only"] is True


def test_pact_token_estimate():
    """Token estimate is reasonable."""
    record = PACTRecord(
        task_id="test-003",
        route_risk_tier="low",
        candidate_ids=["A"],
        recommended_candidate_id="A",
    )
    tokens = record.token_estimate()
    assert 20 < tokens < 200


def test_validate_pact_valid():
    """Valid PACT record passes validation."""
    record = {
        "task_id": "test-004",
        "route_risk_tier": "low",
        "candidate_ids": ["A"],
        "recommended_candidate_id": "A",
        "observation_only": True,
    }
    errors = validate_pact_record(record)
    assert errors == []


def test_validate_pact_missing_field():
    """Missing required field fails validation."""
    record = {"task_id": "test-005"}
    errors = validate_pact_record(record)
    assert any("Missing required field" in e for e in errors)


def test_validate_pact_invalid_tier():
    """Invalid risk tier fails validation."""
    record = {
        "task_id": "test-006",
        "route_risk_tier": "critical",
        "candidate_ids": ["A"],
        "recommended_candidate_id": "A",
    }
    errors = validate_pact_record(record)
    assert any("Invalid route_risk_tier" in e for e in errors)


def test_validate_pact_forbidden_field():
    """Forbidden field (verdict) fails validation."""
    record = {
        "task_id": "test-007",
        "route_risk_tier": "low",
        "candidate_ids": ["A"],
        "recommended_candidate_id": "A",
        "verdict": "approved",  # Forbidden
    }
    errors = validate_pact_record(record)
    assert any("Forbidden field" in e for e in errors)


def test_validate_pact_low_risk_must_observation():
    """Low-risk must be observation_only=True."""
    record = {
        "task_id": "test-008",
        "route_risk_tier": "low",
        "candidate_ids": ["A"],
        "recommended_candidate_id": "A",
        "observation_only": False,
    }
    errors = validate_pact_record(record)
    assert any("observation_only" in e for e in errors)


def test_pact_from_advisor_output():
    """PACT record can be created from advisor output."""
    from nexus.contracts.s2t_policy import S2TCandidate
    
    candidates = [
        S2TCandidate(candidate_id="A", source="test", content_ref="", selector_score=0.8, verifier_result="pass"),
        S2TCandidate(candidate_id="B", source="test", content_ref="", selector_score=0.6, verifier_result="pass"),
    ]
    advisor_output = {
        "selected_candidate_id": "A",
        "selection_reason_codes": ["high_score"],
    }
    
    record = pact_from_advisor_output("task-001", "low", candidates, advisor_output)
    assert record.task_id == "task-001"
    assert record.route_risk_tier == "low"
    assert record.candidate_ids == ["A", "B"]
    assert record.recommended_candidate_id == "A"
    assert record.observation_only is True
