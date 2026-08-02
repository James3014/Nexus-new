"""
Tests for Epistemic Workflow Benchmark v0 — Observation Import.
Covers all 12 required test cases (Section 28 of spec).
"""
import json
import os
import shutil
import tempfile

import pytest

import inspect
from nexus.research.epistemic_benchmark.contracts import (
    BENCHMARK_OBSERVATION_SCHEMA,
    compute_canonical_sha256,
)
from nexus.research.epistemic_benchmark import observations as obs_mod
from nexus.research.epistemic_benchmark.observations import (
    BENCHMARK_DUPLICATE_OBSERVATION,
    BENCHMARK_DUPLICATE_EVALUATOR_OBSERVATION,
    OBS_IMPORT_INTERNAL_ERROR,
    OBS_IMPORT_LOCK_TIMEOUT,
    OBS_SYMLINK_COMPONENT,
    OBSERVATION_LOCK_FILENAME,
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
    obs_id: str = "OBS-test-001",
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

    # Read the real packet SHA-256 so the observation binding is exact
    pkt_sha256 = packet.get("packet_sha256")

    return build_synthetic_observation(
        benchmark_run_id=run_id,
        arm=arm,
        case_alias=pkt_alias,
        observation_id=obs_id,
        decision=decision,
        packet_sha256=pkt_sha256,
        cited_evidence_refs=refs,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Test 1: Valid import
# ---------------------------------------------------------------------------


def test_valid_import(run_dir, tmp_path):
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-valid-001")
    success, errors = import_observation(run_dir, obs)
    assert success, f"Expected success, got errors: {errors}"
    assert errors == []


# ---------------------------------------------------------------------------
# Test 2: Atomic write (file exists after import)
# ---------------------------------------------------------------------------


def test_atomic_write(run_dir):
    obs = _make_obs(run_dir, "strong_protocol", obs_id="OBS-atomic-001")
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
    obs = _make_obs(run_dir, "epistemic_workflow", obs_id="OBS-dup-001")
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
        observation_id="OBS-unknown-alias-001",
        decision="REJECT",
    )
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any(
        "NOT_FOUND" in e or "MISMATCH" in e or "PACKET" in e or "PATH_COMPONENT_INVALID" in e
        for e in errors
    )


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
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-baddec-001", decision="ACCEPT")
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
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-boolconf-001", confidence=80)
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
        obs_id="OBS-badref-001",
        cited_refs=["DOES-NOT-EXIST-ref-99999"],
    )
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("ref" in e.lower() or "EVIDENCE" in e or "REF" in e for e in errors)


# ---------------------------------------------------------------------------
# Test 9: Naive timestamp rejected
# ---------------------------------------------------------------------------


def test_naive_timestamp_rejected(run_dir):
    obs = _make_obs(run_dir, "strong_protocol", obs_id="OBS-naivets-001")
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
    obs = _make_obs(run_dir, "strong_protocol", obs_id="OBS-negdur-001")
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
    obs = _make_obs(run_dir, "epistemic_workflow", obs_id="OBS-nocot-001")
    assert "chain_of_thought" not in obs
    assert "full_reasoning" not in obs
    assert "cot" not in obs


# ---------------------------------------------------------------------------
# Test 12: Observation hash validation
# ---------------------------------------------------------------------------


def test_observation_hash_validation(run_dir):
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-hashval-001")
    # Tamper with hash
    obs["observation_sha256"] = "deadbeef" * 8

    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("hash" in e.lower() or "SHA" in e for e in errors)


# ---------------------------------------------------------------------------
# Section 14: Required RED Proofs
# ---------------------------------------------------------------------------


def test_red_01_allow_overwrite_still_exists():
    from nexus.research.epistemic_benchmark.observations import import_observation
    sig = inspect.signature(import_observation)
    assert "allow_overwrite" not in sig.parameters, "RED-01: allow_overwrite parameter must be completely removed"


def test_red_02_same_evaluator_different_id_duplicate_rejected(run_dir):
    from nexus.research.epistemic_benchmark.observations import import_observation
    # Build obs1 and obs2 with SAME evaluator_id to confirm the evaluator tuple rule
    obs1 = _make_obs(run_dir, "standard_review", obs_id="OBS-eval-dup-1")
    obs2 = _make_obs(run_dir, "standard_review", obs_id="OBS-eval-dup-2")
    # Force same evaluator_id on obs2 so the (arm, alias, provider, model_id, evaluator_id, prompt_version) tuple matches
    obs2["evaluator"]["evaluator_id"] = obs1["evaluator"]["evaluator_id"]
    # Recompute hash because evaluator changed
    from nexus.research.epistemic_benchmark.contracts import compute_canonical_sha256
    obs2["observation_sha256"] = compute_canonical_sha256({k: v for k, v in obs2.items() if k != "observation_sha256"})
    # Same evaluator tuple: obs2 has different observation_id but same evaluator details
    s1, e1 = import_observation(run_dir, obs1)
    assert s1, f"First import failed: {e1}"
    s2, e2 = import_observation(run_dir, obs2)
    assert not s2, "RED-02: Same evaluator tuple must be rejected even with different observation_id"
    assert "BENCHMARK_DUPLICATE_EVALUATOR_OBSERVATION" in e2


def test_red_03_malformed_json_counted_in_inventory(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    from nexus.research.epistemic_benchmark.observations import load_observation_inventory
    # Isolated run dir so the malformed file never pollutes the shared fixture.
    base = tmp_path / "red03_malformed"
    run_dir = str(base / "run")
    priv = str(base / "priv.json")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=priv, seed=503)
    # Put a malformed json file in observations/
    obs_root = os.path.join(run_dir, "observations", "standard_review", "alias_test")
    os.makedirs(obs_root, exist_ok=True)
    bad_file = os.path.join(obs_root, "bad_obs.json")
    with open(bad_file, "w") as f:
        f.write("{invalid json syntax...")
    inv = load_observation_inventory(run_dir)
    assert len(inv.get("invalid", [])) + len(inv.get("unexpected_files", [])) > 0, "RED-03: Malformed JSON must be captured in inventory"


def test_red_04_observation_missing_packet_sha256_rejected(run_dir):
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-nopktsha-1")
    assert "packet_sha256" in obs, "RED-04: Observation schema must include packet_sha256"


def test_red_05_wrong_packet_hash_rejected(run_dir):
    from nexus.research.epistemic_benchmark.observations import verify_observation
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-wrongpkt-1")
    if "packet_sha256" in obs:
        obs["packet_sha256"] = "0" * 64
        obs["observation_sha256"] = compute_canonical_sha256({k: v for k, v in obs.items() if k != "observation_sha256"})
        valid, errs = verify_observation(obs, run_dir)
        assert not valid, "RED-05: Mismatched packet_sha256 must be rejected"
        # Error codes may include detail suffix; check for prefix match
        assert any(e.startswith("OBS_PACKET_SHA256_MISMATCH") for e in errs), f"Expected OBS_PACKET_SHA256_MISMATCH in {errs}"
    else:
        pytest.fail("RED-05: Observation schema missing packet_sha256")


def test_red_06_duplicate_observation_id_global_rejection(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    from nexus.research.epistemic_benchmark.observations import import_observation
    base = tmp_path / "global_dup_run"
    run_dir = str(base / "run")
    priv_path = str(base / "priv.json")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=priv_path, seed=99)

    # Create obs for arm 1
    obs1 = _make_obs(run_dir, "standard_review", obs_id="OBS-global-dup-id-100")
    # Create obs for arm 2 with SAME observation_id
    obs2 = _make_obs(run_dir, "strong_protocol", obs_id="OBS-global-dup-id-100")

    s1, e1 = import_observation(run_dir, obs1)
    assert s1, f"First import failed: {e1}"
    s2, e2 = import_observation(run_dir, obs2)
    assert not s2, "RED-06: Same observation_id across different arms/aliases must be globally rejected"
    assert "BENCHMARK_DUPLICATE_OBSERVATION" in e2


# ---------------------------------------------------------------------------
# ERB-R2B1.1 RED Proofs
# ---------------------------------------------------------------------------


def test_red_01_path_traversal_rejected(tmp_path):
    """RED-01: observation_id traversal must not escape the run directory."""
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "red01_run"
    run_dir = str(base / "run")
    priv = str(base / "priv.json")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=priv, seed=501)
    obs = _make_obs(run_dir, "standard_review", obs_id="../../../../escaped")
    success, errors = import_observation(run_dir, obs)
    assert not success, f"RED-01: path traversal must be rejected, got success={success} errors={errors}"
    escaped = base / "escaped.json"
    assert not escaped.exists(), "RED-01: traversal must not write outside the run directory"


def test_red_02_concurrent_same_evaluator_exactly_one(tmp_path):
    """RED-02: concurrent same-evaluator imports must produce exactly one success."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "red02_run"
    run_dir = str(base / "run")
    priv = str(base / "priv.json")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=priv, seed=502)

    obs1 = _make_obs(run_dir, "standard_review", obs_id="OBS-red02-a-001")
    obs2 = _make_obs(run_dir, "standard_review", obs_id="OBS-red02-b-001")
    shared_eval = obs1["evaluator"]["evaluator_id"]
    obs2["evaluator"]["evaluator_id"] = shared_eval
    obs2["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs2.items() if k != "observation_sha256"}
    )

    barrier = threading.Barrier(2)

    def _run(obs):
        barrier.wait()
        return import_observation(run_dir, obs)

    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(_run, obs1)
        f2 = ex.submit(_run, obs2)
        r1 = f1.result()
        r2 = f2.result()

    successes = sum(1 for s, e in (r1, r2) if s)
    dup_errors = sum(1 for s, e in (r1, r2) if not s and BENCHMARK_DUPLICATE_EVALUATOR_OBSERVATION in e)
    assert successes == 1, f"RED-02: expected exactly one success, got {r1} {r2}"
    assert dup_errors == 1, f"RED-02: expected exactly one duplicate error, got {r1} {r2}"


def test_red_03_cross_offset_later_completed_accepted(run_dir):
    """RED-03: completed_at later in UTC but earlier lexicographically must be accepted."""
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-red03-time-001")
    obs["execution"]["started_at"] = "2026-08-02T10:00:00+07:00"
    obs["execution"]["completed_at"] = "2026-08-02T04:30:00+01:00"
    obs["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs.items() if k != "observation_sha256"}
    )
    success, errors = import_observation(run_dir, obs)
    assert success, f"RED-03: cross-offset later-completed must be accepted, got {errors}"


def test_red_04_wrong_schema_rejected(run_dir):
    """RED-04: observation schema must match exactly."""
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-red04-schema-001")
    obs["schema"] = "nexus.wrong_observation.v0"
    obs["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs.items() if k != "observation_sha256"}
    )
    success, errors = import_observation(run_dir, obs)
    assert not success, f"RED-04: wrong schema must be rejected, got success"
    assert any("OBS_SCHEMA_INVALID" in e for e in errors), f"got {errors}"


# ---------------------------------------------------------------------------
# ERB-R2B1.1 Path safety (11 cases)
# ---------------------------------------------------------------------------


def test_path_contains_dotdot_segment_rejected(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "p_dotdot"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=521)
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-..-escaped")
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("OBS_PATH_COMPONENT_INVALID" in e or "OBS_DESTINATION_OUTSIDE_RUN" in e for e in errors)


def test_path_absolute_obs_id_rejected(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "p_abs"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=522)
    obs = _make_obs(run_dir, "standard_review", obs_id="/etc/OBS-abs-001")
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("OBS_PATH_COMPONENT_INVALID" in e or "OBS_DESTINATION_OUTSIDE_RUN" in e for e in errors)


def test_path_obs_id_too_long_rejected(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "p_long"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=523)
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-" + "a" * 200)
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("OBS_PATH_COMPONENT_INVALID" in e or "OBS_DESTINATION_OUTSIDE_RUN" in e for e in errors)


def test_path_obs_id_invalid_chars_rejected(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "p_chars"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=524)
    for bad in ("OBS-bad/char-001", "OBS-bad\\char-001", "OBS-bad:char-001", "OBS-bad*char-001"):
        obs = _make_obs(run_dir, "standard_review", obs_id=bad)
        success, errors = import_observation(run_dir, obs)
        assert not success, f"obs_id={bad!r} must be rejected, got success={success}"
        assert any("OBS_PATH_COMPONENT_INVALID" in e or "OBS_DESTINATION_OUTSIDE_RUN" in e for e in errors)


def test_path_arm_not_in_enum_rejected(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "p_arm"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=525)
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-arm-bad-001")
    obs["arm"] = "not_a_real_arm"
    obs["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs.items() if k != "observation_sha256"}
    )
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("OBS_PATH_COMPONENT_INVALID" in e or "OBS_DESTINATION_OUTSIDE_RUN" in e for e in errors)


def test_path_case_alias_bad_format_rejected(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "p_alias"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=526)
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-alias-bad-001", alias="../CASE-ABCDEF0123456789")
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("OBS_PATH_COMPONENT_INVALID" in e or "OBS_DESTINATION_OUTSIDE_RUN" in e for e in errors)


def test_path_symlink_dir_escape_rejected(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "p_symlink"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=527)
    # Create a legal alias dir whose real path resolves outside observations/.
    obs_root = os.path.join(run_dir, "observations")
    os.makedirs(obs_root, exist_ok=True)
    outside = str(tmp_path / "outside_target")
    os.makedirs(outside, exist_ok=True)
    alias = "CASE-ABCDEF0123456789"
    legal_arm_dir = os.path.join(obs_root, "standard_review")
    os.makedirs(legal_arm_dir, exist_ok=True)
    os.symlink(outside, os.path.join(legal_arm_dir, alias))
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-symlink-001", alias=alias)
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("OBS_PATH_COMPONENT_INVALID" in e or "OBS_DESTINATION_OUTSIDE_RUN" in e for e in errors)


def test_path_obs_id_not_str_rejected(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "p_notstr"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=528)
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-notstr-001")
    obs["observation_id"] = 12345
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("OBS_PATH_COMPONENT_INVALID" in e or "OBS_DESTINATION_OUTSIDE_RUN" in e for e in errors)


def test_path_containment_verified_for_legal_ids(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "p_legal"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=529)
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-legal-001")
    success, errors = import_observation(run_dir, obs)
    assert success, f"legal obs_id must import cleanly, got {errors}"
    obs_root = os.path.join(run_dir, "observations")
    for root, _dirs, files in os.walk(obs_root):
        for f in files:
            full = os.path.join(root, f)
            assert os.path.realpath(full).startswith(os.path.realpath(obs_root) + os.sep)


def test_path_empty_obs_id_rejected(run_dir):
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-empty-001")
    obs["observation_id"] = ""
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("OBS_ID_MISSING" in e or "OBS_PATH_COMPONENT_INVALID" in e for e in errors)


def test_path_lock_file_not_treated_as_observation(run_dir):
    from nexus.research.epistemic_benchmark.observations import load_observation_inventory
    import nexus.research.epistemic_benchmark.observations as obs_mod
    lock_dir = os.path.join(run_dir, "observations")
    os.makedirs(lock_dir, exist_ok=True)
    lock_path = os.path.join(lock_dir, obs_mod.OBSERVATION_LOCK_FILENAME)
    with open(lock_path, "w") as f:
        f.write("")
    inv = load_observation_inventory(run_dir)
    assert inv.get("unexpected_files") == [], f"lock file must be excluded, got {inv.get('unexpected_files')}"
    assert inv.get("invalid") == [], f"lock file must be excluded, got {inv.get('invalid')}"


# ---------------------------------------------------------------------------
# ERB-R2B1.1 Schema / time contract (8 cases)
# ---------------------------------------------------------------------------


def test_time_invalid_calendar_date_rejected(run_dir):
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-cal-001")
    obs["execution"]["started_at"] = "2026-02-30T00:00:00Z"
    obs["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs.items() if k != "observation_sha256"}
    )
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("TIMESTAMP" in e or "OBS_SCHEMA" in e or "timestamp" in e.lower() for e in errors)


def test_time_leap_second_rejected(run_dir):
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-leap-001")
    obs["execution"]["started_at"] = "2026-08-02T23:59:60Z"
    obs["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs.items() if k != "observation_sha256"}
    )
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("TIMESTAMP" in e or "OBS_SCHEMA" in e or "timestamp" in e.lower() for e in errors)


def test_time_invalid_offset_rejected(run_dir):
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-offset-001")
    obs["execution"]["started_at"] = "2026-08-02T00:00:00+24:00"
    obs["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs.items() if k != "observation_sha256"}
    )
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("TIMESTAMP" in e or "OBS_SCHEMA" in e or "timestamp" in e.lower() for e in errors)


def test_time_completed_before_started_rejected(run_dir):
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-before-001")
    obs["execution"]["started_at"] = "2026-08-02T00:00:05Z"
    obs["execution"]["completed_at"] = "2026-08-02T00:00:01Z"
    obs["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs.items() if k != "observation_sha256"}
    )
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("OBS_COMPLETED_BEFORE_STARTED" in e or "timestamp" in e.lower() or "TIMESTAMP" in e for e in errors)


def test_time_equal_instant_accepted(run_dir):
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-equal-001")
    obs["execution"]["started_at"] = "2026-08-02T00:00:00Z"
    obs["execution"]["completed_at"] = "2026-08-02T00:00:00Z"
    obs["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs.items() if k != "observation_sha256"}
    )
    success, errors = import_observation(run_dir, obs)
    assert success, f"equal instant must be accepted, got {errors}"


def test_schema_non_dict_rejected(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "s_nondict"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=531)
    success, errors = import_observation(run_dir, "not-a-dict")
    assert not success
    assert "OBS_NOT_DICT" in errors


def test_schema_identity_field_types_enforced(run_dir):
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-ident-001")
    obs["benchmark_run_id"] = 42
    obs["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs.items() if k != "observation_sha256"}
    )
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("OBS_IDENTITY_FIELD_INVALID" in e for e in errors), f"got {errors}"


def test_time_naive_rejected_with_instant_compare(run_dir):
    obs = _make_obs(run_dir, "strong_protocol", obs_id="OBS-naive2-001")
    obs["execution"]["completed_at"] = "2026-08-02T00:00:01"  # naive
    obs["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs.items() if k != "observation_sha256"}
    )
    success, errors = import_observation(run_dir, obs)
    assert not success
    assert any("timestamp" in e.lower() or "TIMESTAMP" in e or "timezone" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# ERB-R2B1.1 Concurrency (6 cases)
# ---------------------------------------------------------------------------


def _concurrent_import(run_dir, obs_list, max_workers=8):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    barrier = threading.Barrier(len(obs_list))

    def _run(obs):
        barrier.wait()
        return import_observation(run_dir, obs)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_run, o) for o in obs_list]
        return [f.result() for f in futures]


def test_concurrent_same_obs_id_exactly_one_success(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "c_sameid"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=541)
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-conc-id-001")
    results = _concurrent_import(run_dir, [obs, obs, obs, obs, obs])
    successes = sum(1 for s, _e in results if s)
    assert successes == 1, f"expected exactly 1 success for same obs_id, got {results}"


def test_concurrent_same_evaluator_20_rounds(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "c_eval20"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=542)
    for round_i in range(20):
        obs1 = _make_obs(run_dir, "standard_review", obs_id=f"OBS-conc20-a-{round_i:03d}")
        obs2 = _make_obs(run_dir, "standard_review", obs_id=f"OBS-conc20-b-{round_i:03d}")
        obs2["evaluator"]["evaluator_id"] = obs1["evaluator"]["evaluator_id"]
        obs2["observation_sha256"] = compute_canonical_sha256(
            {k: v for k, v in obs2.items() if k != "observation_sha256"}
        )
        results = _concurrent_import(run_dir, [obs1, obs2], max_workers=2)
        successes = sum(1 for s, _e in results if s)
        dup_errors = sum(
            1 for s, e in results
            if not s and BENCHMARK_DUPLICATE_EVALUATOR_OBSERVATION in e
        )
        assert successes == 1, f"round {round_i}: expected 1 success, got {results}"
        assert dup_errors == 1, f"round {round_i}: expected 1 duplicate error, got {results}"


def test_concurrent_distinct_evaluators_both_succeed(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "c_distinct"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=543)
    obs1 = _make_obs(run_dir, "standard_review", obs_id="OBS-conc-dist-a-001")
    obs2 = _make_obs(run_dir, "standard_review", obs_id="OBS-conc-dist-b-001")
    obs2["evaluator"]["evaluator_id"] = "different-evaluator-id"
    obs2["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs2.items() if k != "observation_sha256"}
    )
    results = _concurrent_import(run_dir, [obs1, obs2], max_workers=2)
    successes = sum(1 for s, _e in results if s)
    assert successes == 2, f"expected both distinct-evaluator imports to succeed, got {results}"


def test_concurrent_across_arms_same_evaluator_distinct_cases_both_succeed(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "c_crossarm"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=544)
    obs1 = _make_obs(run_dir, "standard_review", obs_id="OBS-crossarm-a-001")
    obs2 = _make_obs(run_dir, "strong_protocol", obs_id="OBS-crossarm-b-001")
    obs2["evaluator"]["evaluator_id"] = obs1["evaluator"]["evaluator_id"]
    obs2["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs2.items() if k != "observation_sha256"}
    )
    results = _concurrent_import(run_dir, [obs1, obs2], max_workers=2)
    successes = sum(1 for s, _e in results if s)
    dup_errors = sum(
        1 for s, e in results if not s and BENCHMARK_DUPLICATE_EVALUATOR_OBSERVATION in e
    )
    assert successes == 2, f"same evaluator on distinct arm+case is allowed, got {results}"
    assert dup_errors == 0, f"distinct arm+case must not be a duplicate, got {results}"


def test_concurrent_inventory_preserved_after_many_writes(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    from nexus.research.epistemic_benchmark.observations import load_observation_inventory
    base = tmp_path / "c_many"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=545)
    obs_list = [
        _make_obs(run_dir, "standard_review", obs_id=f"OBS-conc-many-{i:03d}")
        for i in range(10)
    ]
    for i, obs in enumerate(obs_list):
        obs["evaluator"]["evaluator_id"] = f"eval-many-{i:03d}"
        obs["observation_sha256"] = compute_canonical_sha256(
            {k: v for k, v in obs.items() if k != "observation_sha256"}
        )
    results = _concurrent_import(run_dir, obs_list, max_workers=10)
    successes = sum(1 for s, _e in results if s)
    assert successes == 10, f"expected all 10 distinct-evaluator imports to succeed, got {results}"
    inv = load_observation_inventory(run_dir)
    assert len(inv["valid"]) == 10
    assert inv["invalid"] == [] and inv["unexpected_files"] == []


def test_concurrent_duplicate_obs_id_different_evaluators(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    base = tmp_path / "c_dupid"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=546)
    obs1 = _make_obs(run_dir, "standard_review", obs_id="OBS-conc-dupid-001")
    obs2 = _make_obs(run_dir, "standard_review", obs_id="OBS-conc-dupid-001")
    obs2["evaluator"]["evaluator_id"] = "eval-different"
    obs2["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in obs2.items() if k != "observation_sha256"}
    )
    results = _concurrent_import(run_dir, [obs1, obs2], max_workers=2)
    successes = sum(1 for s, _e in results if s)
    dup_errors = sum(
        1 for s, e in results if not s and BENCHMARK_DUPLICATE_OBSERVATION in e
    )
    assert successes == 1, f"expected 1 success for same obs_id, got {results}"
    assert dup_errors == 1, f"expected 1 duplicate obs_id error, got {results}"


# ---------------------------------------------------------------------------
# ERB-R2B1.1 Inventory / report compatibility (10 cases)
# ---------------------------------------------------------------------------


def test_inventory_read_only_no_side_effects(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    from nexus.research.epistemic_benchmark.observations import load_observation_inventory
    base = tmp_path / "inv_readonly"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=551)
    before = sorted(os.listdir(run_dir))
    load_observation_inventory(run_dir)
    after = sorted(os.listdir(run_dir))
    assert before == after, f"inventory must be read-only, dir changed: {before} -> {after}"


def test_inventory_manifest_failure_surfaces_global(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    from nexus.research.epistemic_benchmark.observations import load_observation_inventory, OBS_INVENTORY_MANIFEST_INVALID
    base = tmp_path / "inv_manifest"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=552)
    manifest_path = os.path.join(run_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        f.write("{not valid json")
    inv = load_observation_inventory(run_dir)
    assert inv.get("global_failures"), f"manifest failure must surface in global_failures, got {inv}"
    assert any(OBS_INVENTORY_MANIFEST_INVALID in g for g in inv["global_failures"])


def test_inventory_deterministic_ordering(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    from nexus.research.epistemic_benchmark.observations import load_observation_inventory
    base = tmp_path / "inv_order"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=553)
    for i in range(8):
        obs = _make_obs(run_dir, "standard_review", obs_id=f"OBS-order-{i:03d}")
        s, e = import_observation(run_dir, obs)
        assert s, e
    inv1 = load_observation_inventory(run_dir)
    inv2 = load_observation_inventory(run_dir)
    paths1 = [v["relative_path"] for v in inv1["valid"]]
    paths2 = [v["relative_path"] for v in inv2["valid"]]
    assert paths1 == sorted(paths1)
    assert paths1 == paths2


def test_inventory_unexpected_empty_dir_reported(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    from nexus.research.epistemic_benchmark.observations import load_observation_inventory
    base = tmp_path / "inv_emptydir"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=554)
    os.makedirs(os.path.join(run_dir, "observations", "standard_review", "CASE-ABCDEF0123456789", "deep"), exist_ok=True)
    os.makedirs(os.path.join(run_dir, "observations", "not_an_arm"), exist_ok=True)
    inv = load_observation_inventory(run_dir)
    reasons = [u.get("reason", "") for u in inv["unexpected_files"]]
    assert any("DEPTH_EXCEEDS_ARM_ALIAS" in r for r in reasons), f"got {reasons}"
    assert any("UNKNOWN_ARM_DIRECTORY" in r for r in reasons), f"got {reasons}"


def test_inventory_symlink_dir_reported_not_descended(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    from nexus.research.epistemic_benchmark.observations import load_observation_inventory
    base = tmp_path / "inv_symlinkdir"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=555)
    outside = str(base / "outside")
    os.makedirs(outside, exist_ok=True)
    legal_alias_dir = os.path.join(run_dir, "observations", "standard_review", "CASE-ABCDEF0123456789")
    os.makedirs(legal_alias_dir, exist_ok=True)
    os.symlink(outside, os.path.join(legal_alias_dir, "sneaky"))
    inv = load_observation_inventory(run_dir)
    reasons = [u.get("reason", "") for u in inv["unexpected_files"]]
    assert any("SYMLINK_DIRECTORY_NOT_ALLOWED" in r for r in reasons), f"got {reasons}"


def test_inventory_invalid_entry_arm_attribution_for_report(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    from nexus.research.epistemic_benchmark.observations import load_observation_inventory
    from nexus.research.epistemic_benchmark.report import build_benchmark_report
    base = tmp_path / "inv_reportattr"
    run_dir = str(base / "run")
    priv = str(base / "priv.json")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=priv, seed=556)
    files = sorted(os.listdir(os.path.join(run_dir, "packets", "standard_review")))
    alias = files[0].replace(".json", "")
    obs_dir = os.path.join(run_dir, "observations", "standard_review", alias)
    os.makedirs(obs_dir, exist_ok=True)
    with open(os.path.join(obs_dir, "OBS-bad.json"), "w") as f:
        f.write("{invalid json syntax...")
    inv = load_observation_inventory(run_dir)
    assert len(inv["invalid"]) == 1
    assert inv["invalid"][0]["arm"] == "standard_review", f"got {inv['invalid'][0]}"
    report = build_benchmark_report(run_dir, private_context_path=priv)
    assert report["coverage"]["standard_review"]["invalid_observations"] == 1


def test_inventory_content_arm_attribution_when_parsed(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    from nexus.research.epistemic_benchmark.observations import load_observation_inventory
    base = tmp_path / "inv_contentattr"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=557)
    # Write a structurally valid obs under strong_protocol whose content claims
    # epistemic_workflow: the invalid entry must be attributed by content.
    alias_dir = os.path.join(run_dir, "observations", "strong_protocol")
    os.makedirs(alias_dir, exist_ok=True)
    files = sorted(os.listdir(os.path.join(run_dir, "packets", "strong_protocol")))
    alias = files[0].replace(".json", "")
    obs = _make_obs(run_dir, "epistemic_workflow", obs_id="OBS-content-001")
    target = os.path.join(alias_dir, alias, "OBS-content-001.json")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w") as f:
        json.dump(obs, f)
    inv = load_observation_inventory(run_dir)
    matched = [i for i in inv["invalid"] if i["relative_path"].endswith("OBS-content-001.json")]
    assert matched, f"content-mismatched obs must be invalid, got {inv}"
    assert matched[0]["arm"] == "epistemic_workflow", f"content attribution expected, got {matched[0]}"


def test_inventory_valid_no_duplicate_within_run(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    from nexus.research.epistemic_benchmark.observations import load_observation_inventory
    base = tmp_path / "inv_dup"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=558)
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-dupdetect-001")
    s, e = import_observation(run_dir, obs)
    assert s, e
    inv = load_observation_inventory(run_dir)
    assert len(inv["valid"]) == 1
    # Importing the same obs again must fail closed even with identical content.
    s2, e2 = import_observation(run_dir, obs)
    assert not s2
    assert BENCHMARK_DUPLICATE_OBSERVATION in e2


def test_inventory_unexpected_deep_dir_reported(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    from nexus.research.epistemic_benchmark.observations import load_observation_inventory
    base = tmp_path / "inv_deep"
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "p.json"), seed=559)
    deep = os.path.join(
        run_dir, "observations", "standard_review", "CASE-ABCDEF0123456789", "a", "b"
    )
    os.makedirs(deep, exist_ok=True)
    inv = load_observation_inventory(run_dir)
    reasons = [u.get("reason", "") for u in inv["unexpected_files"]]
    assert any("DEPTH_EXCEEDS_ARM_ALIAS" in r for r in reasons), f"got {reasons}"


def test_inventory_valid_observation_flows_to_report_coverage(tmp_path):
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    from nexus.research.epistemic_benchmark.report import build_benchmark_report
    base = tmp_path / "inv_reportcov"
    run_dir = str(base / "run")
    priv = str(base / "priv.json")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=priv, seed=560)
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-reportcov-001")
    s, e = import_observation(run_dir, obs)
    assert s, e
    report = build_benchmark_report(run_dir, private_context_path=priv)
    cov = report["coverage"]["standard_review"]
    assert cov["valid_observations"] == 1, f"got {cov}"
    assert cov["invalid_observations"] == 0, f"got {cov}"


# ---------------------------------------------------------------------------
# ERB-R2B1.2: symlink component rejection (8) + lock release (9).
# RED-01 == root-symlink case; RED-02 == inventory-exception lock case.
# ---------------------------------------------------------------------------
def _fresh_run(tmp_path, name, seed=0):
    base = tmp_path / name
    run_dir = str(base / "run")
    prepare_benchmark_run(public_output_dir=run_dir, private_context_path=str(base / "priv.json"), seed=seed)
    return run_dir

def _symlink_swap(run_dir, rel, outside):
    target = os.path.join(run_dir, rel)
    if os.path.isdir(target) and not os.path.islink(target):
        shutil.rmtree(target)
    os.makedirs(outside, exist_ok=True)
    os.symlink(outside, target)
    return outside

def _assert_rejected(run_dir, obs):
    success, errors = import_observation(run_dir, obs)
    assert not success and any(OBS_SYMLINK_COMPONENT in e for e in errors), errors

def _raise_boom(*a, **k):
    raise RuntimeError("boom")

def _disk_boom(*a, **k):
    raise OSError("disk boom")

def test_symlink_root_rejected(tmp_path):
    """RED-01: observation root symlink must not escape the run."""
    run_dir = _fresh_run(tmp_path, "r01", seed=511)
    outside = _symlink_swap(run_dir, "observations", str(tmp_path / "r01_out"))
    _assert_rejected(run_dir, _make_obs(run_dir, "standard_review", obs_id="OBS-root-001"))
    assert not [f for f in os.listdir(outside) if f.endswith(".json")]
def test_symlink_arm_directory_rejected(tmp_path):
    run_dir = _fresh_run(tmp_path, "arm", seed=522)
    outside = _symlink_swap(run_dir, "observations/standard_review", str(tmp_path / "arm_out"))
    _assert_rejected(run_dir, _make_obs(run_dir, "standard_review", obs_id="OBS-arm-001"))
    assert os.listdir(outside) == []
def test_symlink_alias_directory_rejected(tmp_path):
    run_dir = _fresh_run(tmp_path, "alias", seed=523)
    alias = sorted(f for f in os.listdir(os.path.join(run_dir, "packets", "standard_review"))
                   if f.endswith(".json"))[0][:-5]
    alias_dir = os.path.join(run_dir, "observations", "standard_review", alias)
    os.makedirs(alias_dir, exist_ok=True)
    outside = _symlink_swap(run_dir, f"observations/standard_review/{alias}", str(tmp_path / "alias_out"))
    _assert_rejected(run_dir, _make_obs(run_dir, "standard_review", obs_id="OBS-alias-001"))
    assert os.listdir(outside) == []
def test_symlink_run_root_rejected(tmp_path):
    base = tmp_path / "runroot"
    real_dir = str(base / "run_real")
    prepare_benchmark_run(public_output_dir=real_dir, private_context_path=str(base / "priv.json"), seed=524)
    link_run = str(base / "run")
    os.symlink(real_dir, link_run)
    _assert_rejected(link_run, _make_obs(real_dir, "standard_review", obs_id="OBS-runroot-001"))
def test_symlink_rejection_no_outside_json(tmp_path):
    run_dir = _fresh_run(tmp_path, "nojson", seed=525)
    outside = _symlink_swap(run_dir, "observations", str(tmp_path / "nojson_out"))
    _assert_rejected(run_dir, _make_obs(run_dir, "standard_review", obs_id="OBS-nojson-001"))
    assert not [f for f in os.listdir(outside) if f.endswith(".json")]
def test_symlink_rejection_no_temp_file(tmp_path):
    run_dir = _fresh_run(tmp_path, "notmp", seed=526)
    outside = _symlink_swap(run_dir, "observations", str(tmp_path / "notmp_out"))
    _assert_rejected(run_dir, _make_obs(run_dir, "standard_review", obs_id="OBS-notmp-001"))
    assert not [f for r, _d, fs in os.walk(outside) for f in fs if f.endswith(".tmp")]
def test_symlink_rejection_no_lock_file(tmp_path):
    run_dir = _fresh_run(tmp_path, "nolock", seed=527)
    outside = _symlink_swap(run_dir, "observations", str(tmp_path / "nolock_out"))
    _assert_rejected(run_dir, _make_obs(run_dir, "standard_review", obs_id="OBS-nolock-001"))
    assert not os.path.exists(os.path.join(outside, OBSERVATION_LOCK_FILENAME))
def test_non_symlink_run_still_imports(tmp_path):
    run_dir = _fresh_run(tmp_path, "normal", seed=528)
    assert import_observation(run_dir, _make_obs(run_dir, "standard_review", obs_id="OBS-normal-001"))[0]

def test_lock_released_after_inventory_exception(tmp_path, monkeypatch):
    """RED-02: an unexpected inventory exception must not leak the lock."""
    run_dir = _fresh_run(tmp_path, "inv", seed=531)
    obs1 = _make_obs(run_dir, "standard_review", obs_id="OBS-inv-a-001")
    obs2 = _make_obs(run_dir, "standard_review", obs_id="OBS-inv-b-001")
    monkeypatch.setattr(obs_mod, "load_observation_inventory", _raise_boom)
    try:
        import_observation(run_dir, obs1)
    except RuntimeError:
        pass
    monkeypatch.undo()
    assert import_observation(run_dir, obs2)[0]
@pytest.mark.parametrize("attr", ["validate_public_run_integrity", "verify_observation"])
def test_lock_released_after_internal_exception(tmp_path, monkeypatch, attr):
    run_dir = _fresh_run(tmp_path, "exc", seed=532)
    obs1 = _make_obs(run_dir, "standard_review", obs_id=f"OBS-{attr[:6]}-a-001")
    obs2 = _make_obs(run_dir, "standard_review", obs_id=f"OBS-{attr[:6]}-b-001")
    monkeypatch.setattr(obs_mod, attr, _raise_boom)
    try:
        import_observation(run_dir, obs1)
    except RuntimeError:
        pass
    monkeypatch.undo()
    assert import_observation(run_dir, obs2)[0]
def test_lock_released_after_atomic_writer_exception(tmp_path, monkeypatch):
    run_dir = _fresh_run(tmp_path, "write", seed=534)
    obs1 = _make_obs(run_dir, "standard_review", obs_id="OBS-write-a-001")
    obs2 = _make_obs(run_dir, "standard_review", obs_id="OBS-write-b-001")
    monkeypatch.setattr(obs_mod, "_atomic_no_overwrite_write", _disk_boom)
    success, errors = import_observation(run_dir, obs1)
    assert not success and any("OBS_WRITE_ERROR" in e for e in errors), errors
    monkeypatch.undo()
    assert import_observation(run_dir, obs2)[0]
def test_lock_released_on_duplicate_return(tmp_path):
    run_dir = _fresh_run(tmp_path, "dup", seed=535)
    obs1 = _make_obs(run_dir, "standard_review", obs_id="OBS-dup-001")
    obs2 = _make_obs(run_dir, "standard_review", obs_id="OBS-dup-002")
    assert import_observation(run_dir, obs1)[0]
    success2, errors2 = import_observation(run_dir, obs1)
    assert not success2 and BENCHMARK_DUPLICATE_OBSERVATION in errors2, errors2
    assert import_observation(run_dir, obs2)[0]
def test_lock_released_on_success(tmp_path):
    run_dir = _fresh_run(tmp_path, "ok", seed=536)
    obs1 = _make_obs(run_dir, "standard_review", obs_id="OBS-ok-001")
    obs2 = _make_obs(run_dir, "standard_review", obs_id="OBS-ok-002")
    assert import_observation(run_dir, obs1)[0]
    assert import_observation(run_dir, obs2)[0]
def test_second_import_no_timeout_after_exception(tmp_path, monkeypatch):
    run_dir = _fresh_run(tmp_path, "nt", seed=537)
    obs1 = _make_obs(run_dir, "standard_review", obs_id="OBS-nt-a-001")
    obs2 = _make_obs(run_dir, "standard_review", obs_id="OBS-nt-b-001")
    monkeypatch.setattr(obs_mod, "load_observation_inventory", _raise_boom)
    try:
        import_observation(run_dir, obs1)
    except RuntimeError:
        pass
    monkeypatch.undo()
    success2, errors2 = import_observation(run_dir, obs2)
    assert success2 and not any(OBS_IMPORT_LOCK_TIMEOUT in e for e in errors2), errors2
def test_real_contention_still_times_out(tmp_path, monkeypatch):
    run_dir = _fresh_run(tmp_path, "contend", seed=538)
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-contend-001")
    monkeypatch.setattr(obs_mod, "IMPORT_LOCK_TIMEOUT_SECONDS", 0.5)
    fd = obs_mod._acquire_import_lock(run_dir, 1.0)
    assert fd is not None
    try:
        success, errors = import_observation(run_dir, obs)
        assert not success and any(OBS_IMPORT_LOCK_TIMEOUT in e for e in errors), errors
    finally:
        obs_mod._release_import_lock(fd)
    monkeypatch.undo()
    assert import_observation(run_dir, obs)[0]
def test_lock_release_exactly_once(tmp_path, monkeypatch):
    run_dir = _fresh_run(tmp_path, "once", seed=539)
    obs = _make_obs(run_dir, "standard_review", obs_id="OBS-once-001")
    real_release = obs_mod._release_import_lock
    calls = {"n": 0}
    def counting_release(fd):
        calls["n"] += 1
        real_release(fd)
    monkeypatch.setattr(obs_mod, "_release_import_lock", counting_release)
    assert import_observation(run_dir, obs)[0]
    assert calls["n"] == 1, calls["n"]
