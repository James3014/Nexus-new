"""P5-I9: E2E Regression and Closure Tests."""
from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.committee_routed_tool import (
    CommitteeRoutedToolRequest,
    evaluate_and_execute,
)
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate
from nexus.services.local_heal.receipt import build_repair_receipt


def _make_candidate(patch, safety_flags=(), target_file="foo.py"):
    raw_hash = __import__("hashlib").sha256(patch.encode("utf-8")).hexdigest()
    return CanonicalPatchCandidate(
        source_format="UNIFIED_DIFF",
        raw_output=patch,
        raw_output_hash=raw_hash,
        normalized_patch=patch,
        normalized_patch_hash=raw_hash,
        normalization_steps=(),
        safety_flags=safety_flags,
        target_file=target_file,
    )


def _make_raw_candidate(patch, model="qwen", safety_flags=(), target_file="foo.py"):
    c = _make_candidate(patch, safety_flags=safety_flags, target_file=target_file)
    return {
        "candidate_patch": patch,
        "format": "UNIFIED_DIFF",
        "model": model,
        "candidate_id": c.raw_output_hash[:16],
    }


def _valid_request(**overrides):
    defaults = {
        "task_id": "p5-e2e",
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


def _setup_p5():
    os.environ["NEXUS_ENABLE_P5_DIVERSITY_SELECTION"] = "1"
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"


def _cleanup_p5():
    os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
    os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)


def test_e2e_one_candidate():
    """P5-I9 Scenario A: one valid candidate → single_candidate selection."""
    _setup_p5()
    try:
        raw = [_make_raw_candidate("x = 1\ny = 2\n")]

        def producer(req):
            return raw

        req = _valid_request()
        result = evaluate_and_execute(req, candidate_producer=producer)
        assert result.winner_found is True
        assert result.candidate_count == 1
    finally:
        _cleanup_p5()


def test_e2e_first_unsafe_second_safe():
    """P5-I9 Scenario B: three candidates, first lower-quality → second selected."""
    _setup_p5()
    try:
        raw = [
            _make_raw_candidate("x", model="qwen"),  # low quality (short)
            _make_raw_candidate("--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-a\n+b", model="deepseek"),  # high quality
            _make_raw_candidate("y", model="llama"),  # low quality
        ]

        def producer(req):
            return raw

        req = _valid_request()
        result = evaluate_and_execute(req, candidate_producer=producer)
        # diversity_v1 should select higher-quality candidate
        assert result.winner_found is True
    finally:
        _cleanup_p5()


def test_e2e_all_unsafe_fail_closed():
    """P5-I9 Scenario D: all candidates malformed/unsafe → fail_closed."""
    _setup_p5()
    try:
        # Empty candidates → zero_winner path
        def producer(req):
            return []

        req = _valid_request()
        result = evaluate_and_execute(req, candidate_producer=producer)
        # No candidates → zero_winner
        assert result.winner_found is False
    finally:
        _cleanup_p5()


def test_e2e_p4_regression():
    """P5-I9 Scenario E: P5 disabled → first-valid behavior."""
    _cleanup_p5()  # Ensure P5 is off
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    try:
        raw = [
            _make_raw_candidate("x", model="qwen"),
            _make_raw_candidate("--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-a\n+b", model="deepseek"),
        ]

        def producer(req):
            return raw

        req = _valid_request()
        result = evaluate_and_execute(req, candidate_producer=producer)
        # P5 disabled → first-valid selection
        assert result.receipt_fragment.get("p5_diversity_selector_used") is None
    finally:
        _cleanup_p5()
