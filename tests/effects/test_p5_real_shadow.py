"""P5-E3: Real Model Candidate Shadow Run Tests."""
from __future__ import annotations

import json
import pytest
from scripts.effects.p5_real_candidate_shadow import run_shadow


def test_shadow_run_no_crash():
    """P5-E3: Shadow run completes without crash."""
    results = run_shadow()
    assert len(results) > 0


def test_shadow_run_has_cases():
    """P5-E3: Shadow run has >= 6 cases."""
    results = run_shadow()
    assert len(results) >= 6


def test_shadow_run_metadata_consistency():
    """P5-E3: Metadata consistency rate is 100%."""
    results = run_shadow()
    for r in results:
        assert r["p5_selected_hash_matches_p4"] is True


def test_shadow_run_trace_coverage():
    """P5-E3: Trace coverage rate is 100%."""
    results = run_shadow()
    for r in results:
        assert r["p5_trace_event_count"] > 0


def test_shadow_run_fuzzy_coverage():
    """P5-E3: Fuzzy backend coverage rate is 100%."""
    results = run_shadow()
    for r in results:
        assert r["p5_fuzzy_backend_used"] is True


def test_shadow_run_no_gate_relaxation():
    """P5-E3: No P2/P4 gate relaxation."""
    results = run_shadow()
    for r in results:
        assert r["apply_status"] == "shadow_only"
        assert r["verifier_status"] == "shadow_only"
