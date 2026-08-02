"""
Tests for Epistemic Workflow Benchmark v0 — Observation Import.
Covers all 12 required test cases (Section 28 of spec).
"""
import json
import os
import tempfile

import pytest

from nexus.research.epistemic_benchmark.contracts import (
    BENCHMARK_OBSERVATION_SCHEMA,
    compute_canonical_sha256,
)
from nexus.research.epistemic_benchmark.observations import (
    BENCHMARK_DUPLICATE_OBSERVATION,
    build_synthetic_observation,
    import_observation,
    import_observation_from_file,
    verify_observation,
    load_valid_observations,
)
from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    """Prepare a real run directory for observation import tests."""
    base = tmp_path_factory.mktemp("obs_run")
    run_dir = str(base / "run")
    priv_path = str(base / "_run_private_context.json")
    prepare_benchmark_run(
        public_output_dir=run_dir,
        private_context_path=priv_path,
        seed=12345,
        corpus_version="v0",
    )
    return run_dir


def _get_first_alias(run_dir: str, arm: str) -> tuple:
    """Return (alias, case_alias) of the first packet in given arm."""
    arm_dir = os.path.join(run_dir, "packets", arm)
    files = [f for f in os.listdir(arm_dir) if f.endswith(".json")]
    assert files, f"No packets found in {arm_dir}"
    alias = files[0].replace(".json", "")
    with open(os.path.join(arm_dir, files[0])) as f:
        packet = json.load(f)
    return alias, packet


def _get_first_evidence_ref(packet: dict) -> str:
    """Return the first available_evidence_ref from the packet."""
    refs = packet.get("common_materials", {}).get("available_evidence_refs", [])
    if refs:
        return refs[0]
    return "mat-001"


def _make_obs(
    run_dir: str,
    arm: str,
    obs_id: str = "obs-test-001",
    decision: str = "ACCEPT",
    confidence: int = 80,
    alias: str = None,
    cited_refs: list = None,
) -> dict:
    """Build a valid observation for the first packet in the given arm."""
    import json as _json
    arm_dir = os.path.join(run_dir, "packets", arm)
    files = sorted([f for f in os.listdir(arm_dir) if f.endswith(".json")])
    pkt_alias = alias or files[0].replace(".json", "")
    with open(os.path.join(arm_dir, files[0])) as f:
        packet = _json.load(f)

    manifest_path = os.path.join(run_dir, "manifest.json")
    with open(manifest_path) as f:
        manifest = _json.load(f)
    run_id = manifest["benchmark_run_id"]

    refs = cited_refs
    if refs is None:
        available = packet.get("common_materials", {}).get("available_evidence_refs", [])
        refs = [available[0]] if available else []

    return build_synthetic_observation(
        benchmark_run_id=run_id,
        arm=arm,
        case_alias=pkt_alias,
        observation_id=obs_id,
        decision=decision,
        cited_evidence_refs=refs,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Test 1: Valid import
# ---------------------------------------------------------------------------


def test_valid_import(run_dir, tmp_path):
    obs = _make_obs(run_dir, "standard_review", obs_id="obs-valid-001")
    success, errors = import_observation(run_dir, obs)
    assert success, f"Expected success, got errors: {errors}"
    assert errors == []


# ---------------------------------------------------------------------------
# Test 2: Atomic write (file exists after import)
# ---------------------------------------------------------------------------


def test_atomic_write(run_dir):
    obs = _make_obs(run_dir, "strong_protocol", obs_id="obs-atomic-001")
    success, errors = import_observation(run_dir, obs)
    assert success

    arm = obs["arm"]
    alias = obs["case_alias"]
    obs_id = obs["observation_id"]
    path = os.path.join(run_dir, "observations", arm, alias, f"{obs_id}.json")
    assert os.path.isfile(path), f"Expected file at {path}"

    with open(path) as f:
        saved = json.load(f)
    assert saved["observation_id"] == obs_id


# ---------------------------------------------------------------------------
# Test 3: Duplicate ID rejected
# ---------------------------------------------------------------------------


def test_duplicate_id_rejected(run_dir):
    obs = _make_obs(run_dir, "epistemic_workflow", obs_id="obs-dup-001")
    success1, _ = import_observation(run_dir, obs)
    assert success1

    success2, errors2 = import_observation(run_dir, obs)
    assert not success2
    assert BENCHMARK_DUPLICATE_OBSERVATION in errors2


# ---------------------------------------------------------------------------
# Test 4: Unknown alias rejected
# ---------------------------------------------------------------------------


def test_unknown_alias_rejected(run_dir):
    manifest_path = os.path.join(run_dir, "manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)
    run_id = manifest["benchmark_run_id"]

    obs = build_synthetic_observation(
        benchmark_run_id=run_id,
        arm="standard_review",
        case_alias="ALIAS-DOES-NOT-EXIST",
        observation_id="obs-unknown-alias-001",
        decision="REJECT",
    )
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("NOT_FOUND" in e or "MISMATCH" in e or "PACKET" in e for e in errors)


# ---------------------------------------------------------------------------
# Test 5: Arm mismatch rejected
# ---------------------------------------------------------------------------


def test_arm_mismatch_rejected(run_dir):
    # Get an alias from standard_review, but claim it's epistemic_workflow
    arm_dir = os.path.join(run_dir, "packets", "standard_review")
    files = sorted([f for f in os.listdir(arm_dir) if f.endswith(".json")])
    alias = files[-1].replace(".json", "")

    manifest_path = os.path.join(run_dir, "manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)
    run_id = manifest["benchmark_run_id"]

    obs = build_synthetic_observation(
        benchmark_run_id=run_id,
        arm="epistemic_workflow",  # wrong arm for this alias
        case_alias=alias,  # alias from standard_review
        observation_id="obs-arm-mismatch-001",
        decision="REJECT",
    )
    success, errors = import_observation(run_dir, obs)
    assert not success, f"Expected failure for arm mismatch, got success"


# ---------------------------------------------------------------------------
# Test 6: Invalid decision rejected
# ---------------------------------------------------------------------------


def test_invalid_decision_rejected(run_dir):
    manifest_path = os.path.join(run_dir, "manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)
    run_id = manifest["benchmark_run_id"]

    # Build a valid obs then tamper with decision
    obs = _make_obs(run_dir, "standard_review", obs_id="obs-baddec-001", decision="ACCEPT")
    obs["decision"] = "MAYBE"  # invalid
    obs["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs.items() if k != "observation_sha256"}
    )

    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("decision" in e.lower() or "DECISION" in e for e in errors)


# ---------------------------------------------------------------------------
# Test 7: Bool confidence rejected
# ---------------------------------------------------------------------------


def test_bool_confidence_rejected(run_dir):
    obs = _make_obs(run_dir, "standard_review", obs_id="obs-boolconf-001", confidence=80)
    obs["confidence"] = True  # bool is not an acceptable int
    obs["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs.items() if k != "observation_sha256"}
    )

    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("confidence" in e.lower() or "CONFIDENCE" in e for e in errors)


# ---------------------------------------------------------------------------
# Test 8: Invalid evidence ref rejected
# ---------------------------------------------------------------------------


def test_invalid_evidence_ref_rejected(run_dir):
    obs = _make_obs(
        run_dir,
        "standard_review",
        obs_id="obs-badref-001",
        cited_refs=["DOES-NOT-EXIST-ref-99999"],
    )
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("ref" in e.lower() or "EVIDENCE" in e or "REF" in e for e in errors)


# ---------------------------------------------------------------------------
# Test 9: Naive timestamp rejected
# ---------------------------------------------------------------------------


def test_naive_timestamp_rejected(run_dir):
    obs = _make_obs(run_dir, "strong_protocol", obs_id="obs-naivets-001")
    obs["execution"]["started_at"] = "2026-08-02T00:00:00"  # no timezone
    obs["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs.items() if k != "observation_sha256"}
    )

    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("timestamp" in e.lower() or "TIMESTAMP" in e or "timezone" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Test 10: Negative duration rejected
# ---------------------------------------------------------------------------


def test_negative_duration_rejected(run_dir):
    obs = _make_obs(run_dir, "strong_protocol", obs_id="obs-negdur-001")
    obs["execution"]["duration_seconds"] = -1.0
    obs["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs.items() if k != "observation_sha256"}
    )

    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("duration" in e.lower() or "DURATION" in e for e in errors)


# ---------------------------------------------------------------------------
# Test 11: No Chain of Thought field
# ---------------------------------------------------------------------------


def test_no_chain_of_thought_field(run_dir):
    obs = _make_obs(run_dir, "epistemic_workflow", obs_id="obs-nocot-001")
    assert "chain_of_thought" not in obs
    assert "full_reasoning" not in obs
    assert "cot" not in obs


# ---------------------------------------------------------------------------
# Test 12: Observation hash validation
# ---------------------------------------------------------------------------


def test_observation_hash_validation(run_dir):
    obs = _make_obs(run_dir, "standard_review", obs_id="obs-hashval-001")
    # Tamper with hash
    obs["observation_sha256"] = "deadbeef" * 8

    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("hash" in e.lower() or "SHA" in e for e in errors)
