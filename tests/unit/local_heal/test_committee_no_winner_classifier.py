"""B2: Tests for committee no-winner classifier."""
from __future__ import annotations

import pytest

from nexus.services.local_heal.committee_no_winner_classifier import (
    classify_committee_no_winner,
    FAILURE_CLASSES,
)


def test_empty_candidates_classified_as_unknown():
    result = classify_committee_no_winner(candidates=None)
    assert result.failure_class == "UNKNOWN_NEEDS_INSTRUMENTATION"
    assert result.classification_available is False


def test_empty_list_classified_as_unknown():
    result = classify_committee_no_winner(candidates=[])
    assert result.failure_class == "UNKNOWN_NEEDS_INSTRUMENTATION"


def test_winner_exists_not_no_winner():
    result = classify_committee_no_winner(
        candidates=[{"candidate_patch": "x = 1"}],
        winner={"candidate_id": "c1"},
    )
    assert result.has_winner is True
    assert result.classification_available is False


def test_output_quality_ceiling():
    candidates = [
        {"candidate_patch": "", "apply_status": "applied"},
        {"candidate_patch": "x", "apply_status": "applied"},
    ]
    result = classify_committee_no_winner(candidates=candidates)
    assert result.failure_class == "OUTPUT_QUALITY_CEILING"
    assert result.classification_available is True


def test_format_conversion_gap():
    candidates = [
        {"candidate_patch": "x = 1\ny = 2\nz = 3", "apply_status": "format_rejected"},
        {"candidate_patch": "a = 1\nb = 2\nc = 3", "apply_status": "format_rejected"},
    ]
    result = classify_committee_no_winner(candidates=candidates)
    assert result.failure_class == "FORMAT_CONVERSION_GAP"
    assert result.classification_available is True


def test_candidate_isolation_gap():
    candidates = [
        {"candidate_patch": "x = 1\ny = 2\nz = 3", "apply_status": "applied", "rejection_reason": "isolation_applied_hash_mismatch"},
    ]
    result = classify_committee_no_winner(candidates=candidates)
    assert result.failure_class == "CANDIDATE_ISOLATION_GAP"
    assert result.classification_available is True


def test_verifier_evidence_gap():
    candidates = [
        {"candidate_patch": "x = 1\ny = 2\nz = 3\nw = 4", "apply_status": "applied"},
    ]
    result = classify_committee_no_winner(candidates=candidates)
    assert result.failure_class == "VERIFIER_EVIDENCE_GAP"
    assert result.classification_available is True


def test_unknown_needs_instrumentation_insufficient():
    candidates = [
        {"candidate_patch": "x = 1\ny = 2\nz = 3\nw = 4", "apply_status": "applied", "evidence_refs": ["ref1"]},
    ]
    result = classify_committee_no_winner(candidates=candidates)
    assert result.failure_class == "UNKNOWN_NEEDS_INSTRUMENTATION"
    assert result.classification_available is False


def test_all_failure_classes_are_valid():
    for cls in FAILURE_CLASSES:
        assert cls in FAILURE_CLASSES


def test_no_route_authority_drift():
    """Verify classifier has no route/planner/topology imports."""
    import inspect
    from nexus.services.local_heal.committee_no_winner_classifier import classify_committee_no_winner
    source = inspect.getsource(classify_committee_no_winner)
    forbidden = ["CapabilityPlanner", "HybridRouteDecision", "execution_topology", "RouteMode"]
    for token in forbidden:
        assert token not in source, f"Forbidden route token '{token}' found in classifier"
