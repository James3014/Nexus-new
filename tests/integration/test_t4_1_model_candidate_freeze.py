#!/usr/bin/env python3
"""Tests for T4.1 Model Candidate Freeze"""

import json, sys, yaml
from pathlib import Path

NEXUS_ROOT = Path(__file__).resolve().parents[2]


def test_registry_requires_evidence_tier():
    reg = yaml.safe_load((NEXUS_ROOT / "configs/model_candidates/t4_1_frozen_model_candidate_registry.yaml").read_text())
    for c in reg["candidates"]:
        assert c.get("evidence_tier"), f"{c['instance_id']} missing evidence_tier"


def test_source_stale_not_model_failure():
    reg = yaml.safe_load((NEXUS_ROOT / "configs/model_candidates/t4_1_frozen_model_candidate_registry.yaml").read_text())
    for c in reg["candidates"]:
        if "stale" in c.get("source_revision_status", "") or "patched" in c.get("source_revision_status", ""):
            assert not c.get("count_as_model_failure", False), f"{c['instance_id']} counted as model failure"


def test_historical_clean_not_active():
    reg = yaml.safe_load((NEXUS_ROOT / "configs/model_candidates/t4_1_frozen_model_candidate_registry.yaml").read_text())
    for c in reg["candidates"]:
        if "stale" in c.get("source_revision_status", "") or "patched" in c.get("source_revision_status", ""):
            assert c.get("evidence_tier") != "active_replayable", f"{c['instance_id']} is historical but active_replayable"


def test_replay_manifest_excludes_unknown():
    manifest = yaml.safe_load((NEXUS_ROOT / "configs/model_candidates/t4_1_t4_2_clean_room_replay_manifest.yaml").read_text())
    for c in manifest.get("replay_candidates", []):
        assert "unknown" not in c.get("source_snapshot_hash", ""), f"{c['instance_id']} has unknown hash"


def test_model_calls_0_no_reward():
    reg = yaml.safe_load((NEXUS_ROOT / "configs/model_candidates/t4_1_frozen_model_candidate_registry.yaml").read_text())
    for c in reg["candidates"]:
        if c.get("model_calls", 0) == 0:
            assert c.get("model_patch_reward", 0) == 0.0, f"{c['instance_id']} model_calls=0 but reward>0"


def test_public_claim_false():
    reg = yaml.safe_load((NEXUS_ROOT / "configs/model_candidates/t4_1_frozen_model_candidate_registry.yaml").read_text())
    for c in reg["candidates"]:
        assert not c.get("public_claim_allowed", False), f"{c['instance_id']} public_claim_allowed=true"
        assert not c.get("export_as_public_claim", False), f"{c['instance_id']} export_as_public_claim=true"


def test_deterministic_fallback_not_model_success():
    """deterministic_fallback_used=true with model_calls=0 should not have model_patch_reward>0."""
    reg = yaml.safe_load((NEXUS_ROOT / "configs/model_candidates/t4_1_frozen_model_candidate_registry.yaml").read_text())
    for c in reg["candidates"]:
        if c.get("deterministic_fallback_used", False) and c.get("model_calls", 0) == 0:
            assert c.get("model_patch_reward", 0) == 0.0, \
                f"{c['instance_id']} fallback used with model_calls=0 but reward>0"


if __name__ == "__main__":
    test_registry_requires_evidence_tier()
    test_source_stale_not_model_failure()
    test_historical_clean_not_active()
    test_replay_manifest_excludes_unknown()
    test_model_calls_0_no_reward()
    test_public_claim_false()
    test_deterministic_fallback_not_model_success()
    print("All T4.1 tests PASS")
