"""EA-S2: Real Local Candidate Shadow Data Collection Tests."""
from __future__ import annotations

import json
import os
import pytest
from scripts.effects.ea_s2_real_candidate_shadow_batch import collect_shadow_data


def _load_shadow_data():
    rows = collect_shadow_data()
    return rows


def test_shadow_data_collected():
    """EA-S2: Shadow data is collected."""
    rows = _load_shadow_data()
    assert len(rows) > 0


def test_real_model_output_case_count():
    """EA-S2: real_model_output_case_count >= 20."""
    rows = _load_shadow_data()
    real_count = sum(1 for r in rows if r["real_model_output"] is True)
    assert real_count >= 20


def test_candidate_count_gte_2():
    """EA-S2: candidate_count >= 2 cases >= 10."""
    rows = _load_shadow_data()
    count_2plus = sum(1 for r in rows if r["candidate_count"] >= 2)
    assert count_2plus >= 10


def test_metadata_consistency_rate():
    """EA-S2: metadata_consistency_rate = 100%."""
    rows = _load_shadow_data()
    for r in rows:
        assert r["p5_selected_hash_matches_p4"] is True


def test_shadow_output_affects_runtime_false():
    """EA-S2: shadow_output_affects_runtime = false on all cases."""
    rows = _load_shadow_data()
    for r in rows:
        assert r["shadow_output_affects_runtime"] is False


def test_p6_simulator_unsafe_action_count():
    """EA-S2: p6_simulator_unsafe_action_count = 0."""
    rows = _load_shadow_data()
    unsafe_count = sum(1 for r in rows if r["p6_simulator_unsafe_action"] is True)
    assert unsafe_count == 0


def test_memory_pollution_count():
    """EA-S2: memory_pollution_count = 0."""
    rows = _load_shadow_data()
    pollution_count = sum(1 for r in rows if r["memory_pollution_detected"] is True)
    assert pollution_count == 0


def test_fuzzy_calibration_version_present():
    """EA-S2: fuzzy_calibration_version_present_rate = 100%."""
    rows = _load_shadow_data()
    for r in rows:
        assert r["fuzzy_calibration_version"] == "1.0"


def test_claim_gate_relaxation_count():
    """EA-S2: claim_gate_relaxation_count = 0."""
    rows = _load_shadow_data()
    relaxed = sum(1 for r in rows if r["p4_claim_gate_unchanged"] is False)
    assert relaxed == 0


def test_shadow_data_serializable():
    """EA-S2: Shadow data is JSON-serializable."""
    rows = _load_shadow_data()
    json_str = json.dumps(rows, indent=2)
    assert len(json_str) > 0
