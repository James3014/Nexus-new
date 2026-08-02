"""
Epistemic Workflow Benchmark v0 — Packet Tests.

Tests for packets.py: three-arm generation, common materials hash,
oracle leakage prevention, deterministic aliases, and fairness invariants.
"""
import hashlib
import json
import os
import tempfile
from typing import Any, Dict, List

import pytest

from nexus.research.epistemic_benchmark.contracts import (
    BenchmarkArm,
    validate_packet,
    compute_canonical_sha256,
)
from nexus.research.epistemic_benchmark.corpus import (
    REQUIRED_CASE_IDS,
    get_public_corpus,
    get_public_case,
)
from nexus.research.epistemic_benchmark.packets import (
    ARM_C_OVERLAY,
    ORACLE_FORBIDDEN_STRINGS,
    REAL_CASE_IDS,
    STRONG_PROTOCOL_CHECKLIST,
    STRONG_PROTOCOL_VERSION,
    compute_common_materials_sha256,
    generate_case_alias,
    prepare_benchmark_run,
    scan_packet_for_oracle_leakage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _prepare_run(seed: int = 20260802) -> tuple:
    """Return (run_dir, run_id, manifest) for a fresh temporary run."""
    tmp = tempfile.mkdtemp()
    manifest = prepare_benchmark_run(tmp, seed)
    run_id = manifest["benchmark_run_id"]
    run_dir = tmp
    return run_dir, run_id, manifest


# ---------------------------------------------------------------------------
# Test 1: Three arms generated
# ---------------------------------------------------------------------------


def test_three_arms_generated():
    run_dir, run_id, manifest = _prepare_run()
    arms = manifest["arms"]
    assert set(arms) == {"standard_review", "strong_protocol", "epistemic_workflow"}


def test_packet_dirs_exist():
    run_dir, run_id, manifest = _prepare_run()
    for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
        arm_dir = os.path.join(run_dir, "packets", arm)
        assert os.path.isdir(arm_dir), f"Missing arm dir: {arm}"


def test_18_packets_per_arm():
    run_dir, run_id, manifest = _prepare_run()
    for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
        arm_dir = os.path.join(run_dir, "packets", arm)
        packets = [f for f in os.listdir(arm_dir) if f.endswith(".json")]
        assert len(packets) == 18, f"arm={arm}: expected 18 packets, got {len(packets)}"


# ---------------------------------------------------------------------------
# Test 2: Same common materials hash across arms
# ---------------------------------------------------------------------------


def test_common_materials_hash_equal_across_arms():
    """All three arms for the same case must have the same common_materials_sha256."""
    run_dir, run_id, manifest = _prepare_run()
    packet_manifest = manifest["packet_manifest"]

    for case_id, arm_aliases in packet_manifest.items():
        hashes = {}
        for arm_name, alias in arm_aliases.items():
            pkt_path = os.path.join(run_dir, "packets", arm_name, f"{alias}.json")
            with open(pkt_path, "r", encoding="utf-8") as f:
                packet = json.load(f)
            hashes[arm_name] = packet["common_materials_sha256"]

        assert len(set(hashes.values())) == 1, (
            f"{case_id}: common_materials_sha256 differs across arms: {hashes}"
        )


def test_common_materials_hash_matches_computation():
    """common_materials_sha256 must be recomputable from the packet's common_materials."""
    run_dir, run_id, manifest = _prepare_run()
    case_id = "EBR-001"
    aliases = manifest["packet_manifest"][case_id]
    case = get_public_case(case_id)
    expected_hash = compute_common_materials_sha256(case)

    for arm_name, alias in aliases.items():
        pkt_path = os.path.join(run_dir, "packets", arm_name, f"{alias}.json")
        with open(pkt_path, "r", encoding="utf-8") as f:
            packet = json.load(f)
        assert packet["common_materials_sha256"] == expected_hash, (
            f"{arm_name}: common_materials_sha256 mismatch for {case_id}"
        )


def test_common_materials_content_equal_across_arms():
    """The actual common_materials dict must be identical across all arms."""
    run_dir, run_id, manifest = _prepare_run()
    packet_manifest = manifest["packet_manifest"]
    arm_names = list(packet_manifest[REQUIRED_CASE_IDS[0]].keys())

    for case_id, arm_aliases in packet_manifest.items():
        payloads = {}
        for arm_name, alias in arm_aliases.items():
            pkt_path = os.path.join(run_dir, "packets", arm_name, f"{alias}.json")
            with open(pkt_path, "r", encoding="utf-8") as f:
                packet = json.load(f)
            payloads[arm_name] = _canonical(packet["common_materials"])

        unique_payloads = set(payloads.values())
        assert len(unique_payloads) == 1, (
            f"{case_id}: common_materials differ across arms"
        )


# ---------------------------------------------------------------------------
# Test 3: Strong Protocol checklist completeness
# ---------------------------------------------------------------------------


def test_strong_protocol_checklist_has_14_items():
    assert len(STRONG_PROTOCOL_CHECKLIST) == 14


def test_strong_protocol_checklist_covers_required_topics():
    combined = " ".join(STRONG_PROTOCOL_CHECKLIST).lower()
    required_topics = [
        "mandatory check",
        "unique test",
        "skipped",
        "read-only",
        "artifact",
        "cross-run",
        "cross-claim",
        "valid-hash semantic",
        "authority",
        "negative",
        "block",
        "fluent narrative",
        "maximum supportable",
    ]
    for topic in required_topics:
        assert topic in combined, f"Checklist missing topic: {topic!r}"


def test_strong_protocol_not_weakened():
    """Arm B overlay must have the full checklist, not a dummy or empty one."""
    from nexus.research.epistemic_benchmark.packets import ARM_B_OVERLAY
    checklist = ARM_B_OVERLAY.get("checklist", [])
    assert len(checklist) >= 14, "Arm B checklist is too short — weakened!"
    # Must not contain instructions to trust implementer or skip evidence
    combined = " ".join(checklist).lower()
    assert "trust the implementer" not in combined
    assert "skip evidence" not in combined


# ---------------------------------------------------------------------------
# Test 4: Epistemic arm also contains the same Strong Protocol checklist
# ---------------------------------------------------------------------------


def test_epistemic_arm_has_same_checklist_as_strong_protocol():
    from nexus.research.epistemic_benchmark.packets import ARM_B_OVERLAY, ARM_C_OVERLAY
    assert ARM_C_OVERLAY.get("checklist") == ARM_B_OVERLAY.get("checklist"), (
        "Arm C must use the same STRONG_PROTOCOL_V1 checklist as Arm B"
    )


def test_arm_c_protocol_version_matches_arm_b():
    from nexus.research.epistemic_benchmark.packets import ARM_B_OVERLAY, ARM_C_OVERLAY
    assert ARM_C_OVERLAY.get("protocol") == ARM_B_OVERLAY.get("protocol")


# ---------------------------------------------------------------------------
# Test 5: Arm C has no extra source facts beyond Arm B
# ---------------------------------------------------------------------------


def test_arm_c_no_extra_source_facts():
    """Arm C overlay may add epistemic structure but not new source materials."""
    run_dir, run_id, manifest = _prepare_run()
    packet_manifest = manifest["packet_manifest"]

    for case_id, arm_aliases in packet_manifest.items():
        arm_b_alias = arm_aliases["strong_protocol"]
        arm_c_alias = arm_aliases["epistemic_workflow"]

        pkt_b_path = os.path.join(run_dir, "packets", "strong_protocol", f"{arm_b_alias}.json")
        pkt_c_path = os.path.join(run_dir, "packets", "epistemic_workflow", f"{arm_c_alias}.json")

        with open(pkt_b_path, "r", encoding="utf-8") as f:
            pkt_b = json.load(f)
        with open(pkt_c_path, "r", encoding="utf-8") as f:
            pkt_c = json.load(f)

        # Common materials must be strictly identical
        assert _canonical(pkt_b["common_materials"]) == _canonical(pkt_c["common_materials"]), (
            f"{case_id}: Arm C common_materials differs from Arm B"
        )


# ---------------------------------------------------------------------------
# Test 6: Aliases differ across arms for the same case
# ---------------------------------------------------------------------------


def test_aliases_differ_across_arms_for_same_case():
    run_dir, run_id, manifest = _prepare_run()
    for case_id, arm_aliases in manifest["packet_manifest"].items():
        aliases = list(arm_aliases.values())
        assert len(aliases) == len(set(aliases)), (
            f"{case_id}: same alias used across multiple arms"
        )


# ---------------------------------------------------------------------------
# Test 7: Same seed is deterministic
# ---------------------------------------------------------------------------


def test_same_seed_deterministic():
    tmp1 = tempfile.mkdtemp()
    tmp2 = tempfile.mkdtemp()
    m1 = prepare_benchmark_run(tmp1, seed=999)
    m2 = prepare_benchmark_run(tmp2, seed=999)

    # run_ids should be equal (same seed)
    assert m1["benchmark_run_id"] == m2["benchmark_run_id"]

    # Packet aliases must be identical
    assert m1["packet_manifest"] == m2["packet_manifest"]


def test_packet_content_deterministic_same_seed():
    tmp1 = tempfile.mkdtemp()
    tmp2 = tempfile.mkdtemp()
    m1 = prepare_benchmark_run(tmp1, seed=777)
    m2 = prepare_benchmark_run(tmp2, seed=777)
    run_id = m1["benchmark_run_id"]

    run_dir1 = tmp1
    run_dir2 = tmp2

    # Check one packet from each arm
    case_id = "EBR-001"
    for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
        alias = m1["packet_manifest"][case_id][arm]
        pkt1 = os.path.join(run_dir1, "packets", arm, f"{alias}.json")
        pkt2 = os.path.join(run_dir2, "packets", arm, f"{alias}.json")
        with open(pkt1) as f1, open(pkt2) as f2:
            assert f1.read() == f2.read(), f"packet content differs for {arm}/{case_id}"


# ---------------------------------------------------------------------------
# Test 8: Different seed changes aliases and/or order
# ---------------------------------------------------------------------------


def test_different_seed_changes_aliases():
    tmp1 = tempfile.mkdtemp()
    tmp2 = tempfile.mkdtemp()
    m1 = prepare_benchmark_run(tmp1, seed=1)
    m2 = prepare_benchmark_run(tmp2, seed=2)

    # run_ids should differ (different seed)
    assert m1["benchmark_run_id"] != m2["benchmark_run_id"]

    # At least some aliases should differ
    aliases1 = set()
    aliases2 = set()
    for case_arms in m1["packet_manifest"].values():
        aliases1.update(case_arms.values())
    for case_arms in m2["packet_manifest"].values():
        aliases2.update(case_arms.values())

    # Different seeds → different aliases (HMAC over different seed)
    assert aliases1 != aliases2, "Different seeds produced identical aliases"


# ---------------------------------------------------------------------------
# Test 9: No oracle leakage in any packet
# ---------------------------------------------------------------------------


def test_no_oracle_leakage_in_packets():
    run_dir, run_id, manifest = _prepare_run()
    for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
        arm_dir = os.path.join(run_dir, "packets", arm)
        for fname in os.listdir(arm_dir):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(arm_dir, fname), "r", encoding="utf-8") as f:
                packet = json.load(f)
            leaks = scan_packet_for_oracle_leakage(packet)
            assert not leaks, f"Oracle leakage in {arm}/{fname}: {leaks}"


def test_scan_packet_for_oracle_leakage_detects_oracle_class():
    # Build a fake packet with oracle_class injected
    case = get_public_case("EBR-001")
    fake_packet = {
        "schema": "nexus.epistemic_benchmark_packet.v0",
        "benchmark_run_id": "BRN-FAKE",
        "arm": "standard_review",
        "arm_protocol_version": "v0",
        "case_alias": "CASE-FAKE",
        "case_version": "v0",
        "common_materials": {"task_contract": "x", "oracle_class": "CLEAN"},
        "common_materials_sha256": "a" * 64,
        "arm_overlay": {},
        "response_contract": "y",
        "packet_sha256": "b" * 64,
    }
    leaks = scan_packet_for_oracle_leakage(fake_packet)
    assert any("oracle_class" in l or "CLEAN" in l for l in leaks), (
        f"Should have detected oracle_class/CLEAN leak: {leaks}"
    )


# ---------------------------------------------------------------------------
# Test 10: No real case ID in packet JSON
# ---------------------------------------------------------------------------


def test_no_real_case_id_in_packet_json():
    run_dir, run_id, manifest = _prepare_run()
    for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
        arm_dir = os.path.join(run_dir, "packets", arm)
        for fname in os.listdir(arm_dir):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(arm_dir, fname), "r", encoding="utf-8") as f:
                raw = f.read()
            for case_id in REQUIRED_CASE_IDS:
                assert f'"{case_id}"' not in raw, (
                    f"Real case ID {case_id!r} found in {arm}/{fname}"
                )


# ---------------------------------------------------------------------------
# Test 11: No expected answer or oracle decision in response contract
# ---------------------------------------------------------------------------


def test_no_expected_answer_in_response_contract():
    run_dir, run_id, manifest = _prepare_run()
    for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
        arm_dir = os.path.join(run_dir, "packets", arm)
        for fname in os.listdir(arm_dir):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(arm_dir, fname), "r", encoding="utf-8") as f:
                packet = json.load(f)
            # response_contract lists ACCEPT/REJECT/BLOCK as valid options — that is fine.
            # It must NOT pre-reveal the oracle decision or forbidden fields.
            rc = packet.get("response_contract", "")
            assert "expected_answer" not in rc, f"expected_answer leaked in {arm}/{fname}"
            assert "oracle_decision" not in rc, f"oracle_decision leaked in {arm}/{fname}"
            assert "oracle_class" not in rc, f"oracle_class leaked in {arm}/{fname}"
            assert "known_defects" not in rc, f"known_defects leaked in {arm}/{fname}"


# ---------------------------------------------------------------------------
# Test 12: Packet hash is valid and consistent
# ---------------------------------------------------------------------------


def test_all_packet_hashes_valid():
    run_dir, run_id, manifest = _prepare_run()
    for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
        arm_dir = os.path.join(run_dir, "packets", arm)
        for fname in os.listdir(arm_dir):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(arm_dir, fname), "r", encoding="utf-8") as f:
                packet = json.load(f)
            errors = validate_packet(packet)
            assert not errors, f"Packet validation errors in {arm}/{fname}: {errors}"


def test_packet_hashes_recomputable():
    run_dir, run_id, manifest = _prepare_run()
    arm = "standard_review"
    arm_dir = os.path.join(run_dir, "packets", arm)
    for fname in os.listdir(arm_dir):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(arm_dir, fname), "r", encoding="utf-8") as f:
            packet = json.load(f)
        body = {k: v for k, v in packet.items() if k != "packet_sha256"}
        expected = _sha256(_canonical(body))
        assert packet["packet_sha256"] == expected, f"packet_sha256 mismatch: {fname}"


# ---------------------------------------------------------------------------
# Run manifest invariants
# ---------------------------------------------------------------------------


def test_run_manifest_has_no_oracle():
    run_dir, run_id, manifest = _prepare_run()
    manifest_str = _canonical(manifest)
    assert "oracle" not in manifest_str
    assert "oracle_class" not in manifest_str
    assert "known_defects" not in manifest_str


def test_run_dir_has_no_oracle_file():
    run_dir, run_id, manifest = _prepare_run()
    for root, dirs, files in os.walk(run_dir):
        for fname in files:
            lower = fname.lower()
            assert "oracle" not in lower, f"Oracle file found: {os.path.join(root, fname)}"


def test_observations_dir_created():
    run_dir, run_id, manifest = _prepare_run()
    obs_dir = os.path.join(run_dir, "observations")
    assert os.path.isdir(obs_dir)


def test_manifest_has_required_fields():
    run_dir, run_id, manifest = _prepare_run()
    required_keys = {
        "schema", "benchmark_run_id", "corpus_version", "seed",
        "created_at", "arms", "case_count", "packet_manifest", "run_manifest_sha256"
    }
    assert required_keys <= set(manifest.keys())


def test_manifest_case_count():
    run_dir, run_id, manifest = _prepare_run()
    assert manifest["case_count"] == 18


def test_generate_case_alias_deterministic():
    a1 = generate_case_alias("BRN-TEST", "standard_review", "EBR-001", 42)
    a2 = generate_case_alias("BRN-TEST", "standard_review", "EBR-001", 42)
    assert a1 == a2


def test_generate_case_alias_differs_by_arm():
    a_alias = generate_case_alias("BRN-TEST", "standard_review", "EBR-001", 42)
    b_alias = generate_case_alias("BRN-TEST", "strong_protocol", "EBR-001", 42)
    c_alias = generate_case_alias("BRN-TEST", "epistemic_workflow", "EBR-001", 42)
    assert a_alias != b_alias
    assert b_alias != c_alias
    assert a_alias != c_alias
