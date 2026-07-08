"""P5-V2: Runtime SelectionTrace Integration Tests."""
from __future__ import annotations

import json
import os
import pytest
from nexus.services.local_heal.committee_routed_tool import (
    CommitteeRoutedToolRequest,
    evaluate_and_execute,
)


def _make_raw(patch, model="qwen"):
    raw_hash = __import__("hashlib").sha256(patch.encode("utf-8")).hexdigest()
    return {
        "candidate_patch": patch,
        "format": "UNIFIED_DIFF",
        "model": model,
        "candidate_id": raw_hash[:16],
    }


def _valid_request(**overrides):
    defaults = {
        "task_id": "p5-v2",
        "repo_root": "/tmp",
        "target_file": "foo.py",
        "difficulty": "hard",
        "execution_topology": "cloud_with_local_assist",
        "p3_route_status": "shadow_stage5_escalation_recommended",
        "hard_case_escalation_reason": "retry_failed",
        "proposer_specs": [{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
        "judge_model": "judge",
    }
    defaults.update(overrides)
    return CommitteeRoutedToolRequest(**defaults)


def test_trace_events_produced():
    """P5-V2: select_diverse_candidate produces trace events."""
    from nexus.services.local_heal.diversity_selector import select_diverse_candidate
    from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate

    c1 = CanonicalPatchCandidate(
        source_format="UNIFIED_DIFF",
        raw_output="x = 1",
        raw_output_hash="abc",
        normalized_patch="x = 1",
        normalized_patch_hash="abc",
        normalization_steps=(),
        safety_flags=(),
        target_file="foo.py",
    )
    c2 = CanonicalPatchCandidate(
        source_format="UNIFIED_DIFF",
        raw_output="y = 2",
        raw_output_hash="def",
        normalized_patch="y = 2",
        normalized_patch_hash="def",
        normalization_steps=(),
        safety_flags=(),
        target_file="foo.py",
    )
    result = select_diverse_candidate([c1, c2], source_models=["qwen", "deepseek"])

    assert len(result.trace_events) > 0
    event_types = [e["event_type"] for e in result.trace_events]
    assert "candidate_feature_extracted" in event_types
    assert "candidate_duplicate_grouped" in event_types
    assert "popularity_trap_detected" in event_types
    assert "candidate_scored" in event_types


def test_trace_includes_duplicate_grouped():
    """P5-V2: trace includes duplicate_grouped when groups exist."""
    from nexus.services.local_heal.diversity_selector import select_diverse_candidate
    from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate

    c1 = CanonicalPatchCandidate(
        source_format="UNIFIED_DIFF",
        raw_output="x = 1",
        raw_output_hash="abc",
        normalized_patch="x = 1",
        normalized_patch_hash="abc",
        normalization_steps=(),
        safety_flags=(),
        target_file="foo.py",
    )
    c2 = CanonicalPatchCandidate(
        source_format="UNIFIED_DIFF",
        raw_output="x = 1",
        raw_output_hash="abc",
        normalized_patch="x = 1",
        normalized_patch_hash="abc",
        normalization_steps=(),
        safety_flags=(),
        target_file="foo.py",
    )
    result = select_diverse_candidate([c1, c2], source_models=["qwen", "deepseek"])

    dup_events = [e for e in result.trace_events if e["event_type"] == "candidate_duplicate_grouped"]
    assert len(dup_events) == 1
    assert len(dup_events[0]["outputs"]["groups"]) == 1


def test_trace_includes_popularity_trap():
    """P5-V2: trace includes popularity_trap_detected when trap detected."""
    from nexus.services.local_heal.diversity_selector import select_diverse_candidate
    from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate

    c1 = CanonicalPatchCandidate(
        source_format="UNIFIED_DIFF",
        raw_output="x",
        raw_output_hash="abc",
        normalized_patch="x",
        normalized_patch_hash="abc",
        normalization_steps=(),
        safety_flags=(),
        target_file="",
    )
    c2 = CanonicalPatchCandidate(
        source_format="UNIFIED_DIFF",
        raw_output="x",
        raw_output_hash="abc",
        normalized_patch="x",
        normalized_patch_hash="abc",
        normalization_steps=(),
        safety_flags=(),
        target_file="",
    )
    result = select_diverse_candidate([c1, c2], source_models=["qwen", "qwen"])

    trap_events = [e for e in result.trace_events if e["event_type"] == "popularity_trap_detected"]
    assert len(trap_events) == 1
    assert trap_events[0]["outputs"]["detected"] is True


def test_winner_path_includes_scored_event():
    """P5-V2: winner path includes candidate_scored event."""
    from nexus.services.local_heal.diversity_selector import select_diverse_candidate
    from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate

    c1 = CanonicalPatchCandidate(
        source_format="UNIFIED_DIFF",
        raw_output="x = 1",
        raw_output_hash="abc",
        normalized_patch="x = 1",
        normalized_patch_hash="abc",
        normalization_steps=(),
        safety_flags=(),
        target_file="foo.py",
    )
    c2 = CanonicalPatchCandidate(
        source_format="UNIFIED_DIFF",
        raw_output="y = 2",
        raw_output_hash="def",
        normalized_patch="y = 2",
        normalized_patch_hash="def",
        normalization_steps=(),
        safety_flags=(),
        target_file="bar.py",
    )
    result = select_diverse_candidate([c1, c2], source_models=["qwen", "deepseek"])

    scored_events = [e for e in result.trace_events if e["event_type"] == "candidate_scored"]
    assert len(scored_events) == 1
    assert scored_events[0]["decision"] == "selected"


def test_p4_receipt_includes_trace():
    """P5-V2: P4 receipt includes p5_trace_event_count when P5 enabled."""
    os.environ["NEXUS_ENABLE_P5_DIVERSITY_SELECTION"] = "1"
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    try:
        raw = [
            _make_raw("x = 1\ny = 2\n", model="qwen"),
            _make_raw("a = 1\nb = 2\n", model="deepseek"),
        ]

        def producer(req):
            return raw

        req = _valid_request()
        result = evaluate_and_execute(req, candidate_producer=producer)
        assert "p5_trace_event_count" in result.receipt_fragment
        assert result.receipt_fragment["p5_trace_event_count"] > 0
        assert "p5_trace_events" in result.receipt_fragment
    finally:
        os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
        os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)


def test_p4_receipt_no_trace_when_p5_disabled():
    """P5-V2: P4 receipt does NOT include trace when P5 disabled."""
    os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    try:
        raw = [_make_raw("x = 1\ny = 2\n")]

        def producer(req):
            return raw

        req = _valid_request()
        result = evaluate_and_execute(req, candidate_producer=producer)
        assert "p5_trace_event_count" not in result.receipt_fragment
        assert "p5_trace_events" not in result.receipt_fragment
    finally:
        os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)


def test_trace_events_json_serializable():
    """P5-V2: trace events are JSON-serializable."""
    from nexus.services.local_heal.diversity_selector import select_diverse_candidate
    from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate

    c1 = CanonicalPatchCandidate(
        source_format="UNIFIED_DIFF",
        raw_output="x = 1",
        raw_output_hash="abc",
        normalized_patch="x = 1",
        normalized_patch_hash="abc",
        normalization_steps=(),
        safety_flags=(),
        target_file="foo.py",
    )
    result = select_diverse_candidate([c1], source_models=["qwen"])

    json_str = json.dumps(result.trace_events)
    assert len(json_str) > 0
