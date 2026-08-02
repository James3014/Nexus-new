"""
Epistemic Workflow Benchmark v0 — Packet Tests (R2A).

Tests for packets.py: private blinding, public manifest, validators,
three-arm generation, common materials hash, oracle leakage prevention,
deterministic aliases via secret key, and fairness invariants.
"""
import hashlib
import json
import os
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import pytest

from nexus.research.epistemic_benchmark.contracts import (
    BENCHMARK_PRIVATE_CONTEXT_SCHEMA,
    BENCHMARK_PUBLIC_MANIFEST_SCHEMA,
    PRIVATE_CONTEXT_EXACT_KEYS,
    PUBLIC_MANIFEST_EXACT_KEYS,
    PUBLIC_MANIFEST_PACKET_EXACT_KEYS,
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
    ORACLE_FORBIDDEN_STRINGS,
    REAL_CASE_IDS,
    STRONG_PROTOCOL_CHECKLIST,
    STRONG_PROTOCOL_VERSION,
    ARM_A_OVERLAY,
    ARM_B_OVERLAY,
    compute_common_materials_sha256,
    generate_case_alias,
    prepare_benchmark_run,
    scan_packet_for_oracle_leakage,
    validate_public_run_integrity,
    validate_private_scoring_context,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

FIXED_KEY = bytes.fromhex("a1b2c3d4" * 8)  # 32 bytes
ALT_KEY   = bytes.fromhex("deadbeef" * 8)  # 32 bytes, different


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _prepare_run(
    seed: int = 20260802,
    blinding_key: Optional[bytes] = None,
    tmp_dir: Optional[str] = None,
    priv_dir: Optional[str] = None,
) -> Tuple[str, str, Dict, str]:
    """Return (run_dir, priv_path, manifest, priv_ctx_path) for a fresh temporary run."""
    if blinding_key is None:
        blinding_key = FIXED_KEY
    tmp = tmp_dir or tempfile.mkdtemp()
    priv_parent = priv_dir or tempfile.mkdtemp()
    priv_path = os.path.join(priv_parent, "private_context.json")
    manifest = prepare_benchmark_run(
        public_output_dir=tmp,
        private_context_path=priv_path,
        seed=seed,
        blinding_key=blinding_key,
    )
    return tmp, priv_path, manifest, priv_path


# ---------------------------------------------------------------------------
# 1. Public manifest has no case IDs, seed, or alias-to-case map
# ---------------------------------------------------------------------------


def test_public_manifest_no_case_ids():
    """Req #1: Public manifest must not contain real case IDs."""
    run_dir, priv_path, manifest, _ = _prepare_run()
    manifest_str = _canonical(manifest)
    for case_id in REQUIRED_CASE_IDS:
        assert f'"{case_id}"' not in manifest_str, (
            f"Real case ID {case_id!r} found in public manifest"
        )


def test_public_manifest_no_seed():
    """Req #2: Public manifest must not contain the seed."""
    run_dir, priv_path, manifest, _ = _prepare_run(seed=20260802)
    manifest_str = _canonical(manifest)
    assert '"seed"' not in manifest_str, "seed key found in public manifest"
    assert '20260802' not in manifest_str, "seed value found in public manifest"


def test_public_manifest_no_alias_to_case_map():
    """Req #3: Public manifest must not contain alias-to-case mapping."""
    run_dir, priv_path, manifest, _ = _prepare_run()
    manifest_str = _canonical(manifest)
    assert '"alias_to_case"' not in manifest_str
    assert '"packet_manifest"' not in manifest_str
    assert '"case_id"' not in manifest_str


# ---------------------------------------------------------------------------
# 2. Public run has no private context or oracle
# ---------------------------------------------------------------------------


def test_public_run_no_private_context_file():
    """Req #4: Public run directory must not contain private context."""
    run_dir, priv_path, manifest, _ = _prepare_run()
    for root, dirs, files in os.walk(run_dir):
        for fname in files:
            lower = fname.lower()
            assert "private_context" not in lower, (
                f"private_context file found in public run: {os.path.join(root, fname)}"
            )


def test_public_run_no_oracle_file():
    """Req #5: Public run directory must not contain oracle data."""
    run_dir, priv_path, manifest, _ = _prepare_run()
    for root, dirs, files in os.walk(run_dir):
        for fname in files:
            lower = fname.lower()
            assert "oracle" not in lower, (
                f"Oracle file found in public run: {os.path.join(root, fname)}"
            )


# ---------------------------------------------------------------------------
# 3. Private context location enforcement
# ---------------------------------------------------------------------------


def test_private_context_inside_public_run_rejected():
    """Req #6: Reject if private_context_path is inside public_output_dir."""
    tmp = tempfile.mkdtemp()
    priv_path = os.path.join(tmp, "private_context.json")  # inside pub dir!
    with pytest.raises(ValueError, match="PRIVATE_CONTEXT_INSIDE_PUBLIC_RUN"):
        prepare_benchmark_run(
            public_output_dir=tmp,
            private_context_path=priv_path,
            seed=1,
            blinding_key=FIXED_KEY,
        )


def test_existing_private_context_not_overwritten():
    """Req #7: Fail closed if private context already exists."""
    tmp = tempfile.mkdtemp()
    priv_parent = tempfile.mkdtemp()
    priv_path = os.path.join(priv_parent, "private_context.json")
    # Pre-create the private context
    with open(priv_path, "w") as f:
        f.write('{"existing": true}')
    with pytest.raises(FileExistsError, match="PRIVATE_CONTEXT_EXISTS"):
        prepare_benchmark_run(
            public_output_dir=tmp,
            private_context_path=priv_path,
            seed=1,
            blinding_key=FIXED_KEY,
        )


# ---------------------------------------------------------------------------
# 4. Secret-key HMAC alias determinism
# ---------------------------------------------------------------------------


def test_fixed_key_produces_deterministic_aliases():
    """Req #8: Fixed blinding key must produce deterministic aliases."""
    tmp1 = tempfile.mkdtemp()
    tmp2 = tempfile.mkdtemp()
    priv1 = os.path.join(tempfile.mkdtemp(), "priv1.json")
    priv2 = os.path.join(tempfile.mkdtemp(), "priv2.json")

    m1 = prepare_benchmark_run(
        public_output_dir=tmp1, private_context_path=priv1,
        seed=999, blinding_key=FIXED_KEY,
    )
    m2 = prepare_benchmark_run(
        public_output_dir=tmp2, private_context_path=priv2,
        seed=999, blinding_key=FIXED_KEY,
    )
    # Same key + seed → same run_id → same aliases
    assert m1["benchmark_run_id"] == m2["benchmark_run_id"]
    # Compare packet aliases
    pkts1 = {(p["arm"], p["case_alias"]) for p in m1["packets"]}
    pkts2 = {(p["arm"], p["case_alias"]) for p in m2["packets"]}
    assert pkts1 == pkts2


def test_different_key_produces_different_aliases():
    """Req #9: Different blinding key must produce different aliases."""
    tmp1 = tempfile.mkdtemp()
    tmp2 = tempfile.mkdtemp()
    priv1 = os.path.join(tempfile.mkdtemp(), "priv1.json")
    priv2 = os.path.join(tempfile.mkdtemp(), "priv2.json")

    m1 = prepare_benchmark_run(
        public_output_dir=tmp1, private_context_path=priv1,
        seed=1, blinding_key=FIXED_KEY,
    )
    m2 = prepare_benchmark_run(
        public_output_dir=tmp2, private_context_path=priv2,
        seed=1, blinding_key=ALT_KEY,
    )
    pkts1 = {(p["arm"], p["case_alias"]) for p in m1["packets"]}
    pkts2 = {(p["arm"], p["case_alias"]) for p in m2["packets"]}
    assert pkts1 != pkts2, "Different keys produced identical aliases"


def test_public_values_insufficient_to_recompute_alias():
    """Req #10: Alias cannot be recomputed from public values (seed) alone."""
    run_dir, priv_path, manifest, _ = _prepare_run(seed=42)
    # The run_id is public. But without blinding_key, you cannot reproduce alias.
    run_id = manifest["benchmark_run_id"]
    # Even with the run_id and arm name, we cannot guess the alias without key
    first_packet = manifest["packets"][0]
    alias = first_packet["case_alias"]
    arm = first_packet["arm"]

    # Try to regenerate alias using only seed (not key) — should produce different result
    seed_as_key = b"42" * 16  # 32 bytes derived from seed, not real key
    fake_alias = generate_case_alias(run_id, arm, REQUIRED_CASE_IDS[0], seed_as_key)
    # The real alias used FIXED_KEY; seed-based key gives different result
    assert fake_alias != alias, "Alias was recomputable without the secret key"


# ---------------------------------------------------------------------------
# 5. Packet tamper detection
# ---------------------------------------------------------------------------


def test_packet_tamper_without_rehash_rejected():
    """Req #11: Tampered packet (without rehashing) must fail validation."""
    run_dir, priv_path, manifest, _ = _prepare_run()
    pkt_entry = manifest["packets"][0]
    pkt_path = os.path.join(run_dir, pkt_entry["relative_path"])

    with open(pkt_path, "r") as f:
        packet = json.load(f)

    # Tamper without fixing hash
    packet["arm_overlay"] = {"tampered": True}
    with open(pkt_path, "w") as f:
        json.dump(packet, f)

    ok, errors = validate_public_run_integrity(run_dir)
    assert not ok
    assert any("HASH_MISMATCH" in e for e in errors)


def test_packet_tamper_with_rehash_but_manifest_unchanged_rejected():
    """Req #12: Tampered+rehashed packet but manifest unchanged must fail."""
    run_dir, priv_path, manifest, _ = _prepare_run()
    pkt_entry = manifest["packets"][0]
    pkt_path = os.path.join(run_dir, pkt_entry["relative_path"])

    with open(pkt_path, "r") as f:
        packet = json.load(f)

    # Tamper and rehash packet
    packet["arm_overlay"] = {"tampered": True}
    body = {k: v for k, v in packet.items() if k != "packet_sha256"}
    packet["packet_sha256"] = compute_canonical_sha256(body)
    with open(pkt_path, "w") as f:
        json.dump(packet, f)

    # Manifest still has old hash — should fail
    ok, errors = validate_public_run_integrity(run_dir)
    assert not ok
    assert any("HASH_MISMATCH" in e or "MISMATCH" in e for e in errors)


def test_manifest_tamper_with_rehash_but_private_context_unchanged_rejected():
    """Req #13: Tampered+rehashed manifest but private context unchanged must fail."""
    run_dir, priv_path, manifest, _ = _prepare_run()
    manifest_path = os.path.join(run_dir, "manifest.json")

    with open(manifest_path, "r") as f:
        mf = json.load(f)

    # Tamper manifest: change case_count and rehash
    mf["case_count"] = 999
    body = {k: v for k, v in mf.items() if k != "run_manifest_sha256"}
    mf["run_manifest_sha256"] = compute_canonical_sha256(body)
    with open(manifest_path, "w") as f:
        json.dump(mf, f)

    # Private context still has old manifest sha → private context validator fails
    ok, errors = validate_private_scoring_context(run_dir, priv_path)
    assert not ok
    assert any("MANIFEST_SHA" in e or "INVALID" in e or "MISMATCH" in e for e in errors)


# ---------------------------------------------------------------------------
# 6. Packet inventory
# ---------------------------------------------------------------------------


def test_missing_packet_rejected():
    """Req #14: Missing packet must be detected."""
    run_dir, priv_path, manifest, _ = _prepare_run()
    pkt_entry = manifest["packets"][0]
    pkt_path = os.path.join(run_dir, pkt_entry["relative_path"])
    os.unlink(pkt_path)

    ok, errors = validate_public_run_integrity(run_dir)
    assert not ok
    assert any("PACKET_MISSING" in e for e in errors)


def test_extra_packet_rejected():
    """Req #15: Extra packet in run directory must be detected."""
    run_dir, priv_path, manifest, _ = _prepare_run()
    # Add an unexpected packet file
    arm_dir = os.path.join(run_dir, "packets", "standard_review")
    with open(os.path.join(arm_dir, "CASE-EXTRA1234567.json"), "w") as f:
        json.dump({"extra": True}, f)

    ok, errors = validate_public_run_integrity(run_dir)
    assert not ok
    assert any("PACKET_UNEXPECTED" in e for e in errors)


def test_traversal_packet_path_rejected():
    """Req #16: Packet with traversal in relative_path must be rejected."""
    run_dir, priv_path, manifest, _ = _prepare_run()
    manifest_path = os.path.join(run_dir, "manifest.json")

    with open(manifest_path, "r") as f:
        mf = json.load(f)

    # Inject a traversal path into the manifest packets list
    mf["packets"].append({
        "arm": "standard_review",
        "case_alias": "CASE-TRAVERSAL12",
        "relative_path": "../../../etc/passwd",
        "packet_sha256": "a" * 64,
        "common_materials_sha256": "b" * 64,
    })
    with open(manifest_path, "w") as f:
        json.dump(mf, f)

    ok, errors = validate_public_run_integrity(run_dir)
    assert not ok
    assert any("PATH_INVALID" in e for e in errors)


# ---------------------------------------------------------------------------
# 7. Private context validator
# ---------------------------------------------------------------------------


def test_missing_private_binding_rejected():
    """Req #17: Private context missing a binding must fail validation."""
    run_dir, priv_path, manifest, _ = _prepare_run()

    with open(priv_path, "r") as f:
        ctx = json.load(f)

    # Remove one binding
    ctx["alias_bindings"] = ctx["alias_bindings"][1:]
    # Recompute hash
    body = {k: v for k, v in ctx.items() if k != "private_context_sha256"}
    ctx["private_context_sha256"] = compute_canonical_sha256(body)
    with open(priv_path, "w") as f:
        json.dump(ctx, f)

    ok, errors = validate_private_scoring_context(run_dir, priv_path)
    assert not ok
    assert any("MISSING_BINDING" in e or "COVERAGE" in e or "HASH_MISMATCH" in e for e in errors)


def test_extra_private_binding_rejected():
    """Req #18: Private context with extra binding must fail validation."""
    run_dir, priv_path, manifest, _ = _prepare_run()

    with open(priv_path, "r") as f:
        ctx = json.load(f)

    # Add an extra binding
    ctx["alias_bindings"].append({
        "arm": "standard_review",
        "case_alias": "CASE-EXTRA00000000",
        "case_id": "EBR-001",
    })
    body = {k: v for k, v in ctx.items() if k != "private_context_sha256"}
    ctx["private_context_sha256"] = compute_canonical_sha256(body)
    with open(priv_path, "w") as f:
        json.dump(ctx, f)

    ok, errors = validate_private_scoring_context(run_dir, priv_path)
    assert not ok
    assert any("EXTRA_BINDING" in e or "HASH_MISMATCH" in e for e in errors)


def test_unknown_case_binding_rejected():
    """Req #19: Binding with unknown case_id must fail validation."""
    run_dir, priv_path, manifest, _ = _prepare_run()

    with open(priv_path, "r") as f:
        ctx = json.load(f)

    # Replace first binding's case_id with unknown value
    ctx["alias_bindings"][0]["case_id"] = "EBR-INVALID-999"
    body = {k: v for k, v in ctx.items() if k != "private_context_sha256"}
    ctx["private_context_sha256"] = compute_canonical_sha256(body)
    with open(priv_path, "w") as f:
        json.dump(ctx, f)

    ok, errors = validate_private_scoring_context(run_dir, priv_path)
    assert not ok
    assert any("UNKNOWN_CASE_ID" in e or "HASH_MISMATCH" in e for e in errors)


# ---------------------------------------------------------------------------
# 8. Arm C projection requirements
# ---------------------------------------------------------------------------


def test_arm_c_projection_is_case_specific_structured_data():
    """Req #20: Arm C epistemic_structure must be case-specific structured dict."""
    run_dir, priv_path, manifest, _ = _prepare_run()
    for pkt_entry in manifest["packets"]:
        if pkt_entry["arm"] != "epistemic_workflow":
            continue
        pkt_path = os.path.join(run_dir, pkt_entry["relative_path"])
        with open(pkt_path, "r") as f:
            packet = json.load(f)
        overlay = packet.get("arm_overlay", {})
        ep = overlay.get("epistemic_structure")
        assert ep is not None, f"Arm C packet missing epistemic_structure: {pkt_entry['relative_path']}"
        assert isinstance(ep, dict), "epistemic_structure must be a dict"
        # Must have structured keys, not just strings
        assert "object_bindings" in ep or "source_lineage" in ep or "verification_status" in ep, (
            f"epistemic_structure lacks required structured fields: {list(ep.keys())}"
        )


def test_arm_c_projection_not_all_generic_strings():
    """Req #21: Arm C epistemic_structure must not be all generic strings."""
    run_dir, priv_path, manifest, _ = _prepare_run()
    for pkt_entry in manifest["packets"]:
        if pkt_entry["arm"] != "epistemic_workflow":
            continue
        pkt_path = os.path.join(run_dir, pkt_entry["relative_path"])
        with open(pkt_path, "r") as f:
            packet = json.load(f)
        overlay = packet.get("arm_overlay", {})
        ep = overlay.get("epistemic_structure", {})
        # Values should not all be generic string prompts
        string_count = sum(1 for v in ep.values() if isinstance(v, str))
        total = len(ep)
        if total > 0:
            # At least some values should be lists or dicts
            non_string = sum(1 for v in ep.values() if not isinstance(v, str))
            assert non_string > 0, (
                f"Arm C epistemic_structure is all generic strings for {pkt_entry['case_alias']}"
            )


def test_arm_c_projection_evidence_refs_exist_in_case():
    """Req #22: Projection evidence refs must exist in case materials."""
    cases = get_public_corpus()
    from nexus.research.epistemic_benchmark.contracts import CASE_EXACT_KEYS
    for case in cases:
        ep = case.get("epistemic_projection", {})
        if not ep:
            continue
        case_refs = {m.get("ref") for m in case.get("materials", [])}
        case_refs |= set(case.get("available_evidence_refs", []))
        # Check object_bindings evidence_refs
        for binding in ep.get("object_bindings", []):
            for ref in binding.get("evidence_refs", []):
                assert ref in case_refs, (
                    f"Case {case['case_id']}: projection evidence_ref {ref!r} not in materials"
                )


def test_arm_c_projection_no_free_prose_facts():
    """Req #23: Projection must not contain free-prose source facts as strings."""
    # The epistemic_projection in corpus cases uses structured dicts, not prose
    cases = get_public_corpus()
    for case in cases:
        ep = case.get("epistemic_projection", {})
        if not ep:
            continue
        # object_bindings must be list of dicts, not strings
        for binding in ep.get("object_bindings", []):
            assert isinstance(binding, dict), (
                f"Case {case['case_id']}: object_binding should be dict, got {type(binding)}"
            )
            # status must be a closed enum, not free prose
            status = binding.get("status", "")
            assert status in {"BOUND", "MISMATCHED", "MISSING", "UNKNOWN", ""}, (
                f"Case {case['case_id']}: invalid object_binding status {status!r}"
            )


# ---------------------------------------------------------------------------
# 9. Three-arm fairness invariants
# ---------------------------------------------------------------------------


def test_arm_b_and_arm_c_same_checklist():
    """Req #24: Arm B and Arm C must use exactly the same checklist."""
    run_dir, priv_path, manifest, _ = _prepare_run()
    for pkt_entry in manifest["packets"]:
        if pkt_entry["arm"] not in ("strong_protocol", "epistemic_workflow"):
            continue
        pkt_path = os.path.join(run_dir, pkt_entry["relative_path"])
        with open(pkt_path, "r") as f:
            packet = json.load(f)
        overlay = packet.get("arm_overlay", {})
        checklist = overlay.get("checklist", [])
        assert checklist == STRONG_PROTOCOL_CHECKLIST, (
            f"Arm {pkt_entry['arm']} checklist differs from STRONG_PROTOCOL_CHECKLIST"
        )


def test_three_arms_same_common_materials():
    """Req #25: All three arms must have identical common_materials_sha256."""
    run_dir, priv_path, manifest, _ = _prepare_run()
    # Group packets by alias group (use private context to find case groupings)
    with open(priv_path, "r") as f:
        ctx = json.load(f)

    # Build case_id -> {arm: common_sha} from packets
    alias_to_arm_pkt: Dict[str, Dict] = {}
    for pkt_entry in manifest["packets"]:
        alias_to_arm_pkt[(pkt_entry["arm"], pkt_entry["case_alias"])] = pkt_entry

    # Group by case_id
    case_bindings: Dict[str, List] = {}
    for b in ctx["alias_bindings"]:
        cid = b["case_id"]
        if cid not in case_bindings:
            case_bindings[cid] = []
        case_bindings[cid].append(b)

    for case_id, bindings in case_bindings.items():
        shas = {}
        for b in bindings:
            arm = b["arm"]
            alias = b["case_alias"]
            key = (arm, alias)
            if key in alias_to_arm_pkt:
                shas[arm] = alias_to_arm_pkt[key]["common_materials_sha256"]
        if len(shas) == 3:
            assert len(set(shas.values())) == 1, (
                f"Case {case_id}: common_materials_sha256 differs across arms: {shas}"
            )


# ---------------------------------------------------------------------------
# 10. CLI stdout has no private data
# ---------------------------------------------------------------------------


def test_cli_prepare_run_stdout_no_private_data(tmp_path, capsys):
    """Req #26: CLI prepare-run stdout must not expose seed, key, case IDs, or oracle."""
    from nexus.research.epistemic_benchmark.cli import main

    pub_dir = str(tmp_path / "pub_run")
    priv_file = str(tmp_path / "priv.json")

    ret = main([
        "prepare-run",
        "--output", pub_dir,
        "--private-context", priv_file,
        "--seed", "12345",
    ])
    captured = capsys.readouterr()
    assert ret == 0, f"CLI returned non-zero: {captured.err}"
    stdout = captured.out
    # Must not contain seed value
    assert "12345" not in stdout, "Seed found in CLI stdout"
    # Must not contain any real case ID
    for case_id in REQUIRED_CASE_IDS:
        assert case_id not in stdout, f"Case ID {case_id!r} found in CLI stdout"
    # Must have the success token
    assert "RUN_PREPARED" in stdout


# ---------------------------------------------------------------------------
# 11. Failure cleanup
# ---------------------------------------------------------------------------


def test_preparation_failure_no_partial_public_run():
    """Req #27: Failed preparation must not leave partial public run."""
    # Force failure by providing existing non-empty public run dir
    tmp_run = tempfile.mkdtemp()
    # Make it non-empty
    with open(os.path.join(tmp_run, "existing.txt"), "w") as f:
        f.write("existing")
    priv_path = os.path.join(tempfile.mkdtemp(), "priv.json")

    with pytest.raises((FileExistsError, ValueError)):
        prepare_benchmark_run(
            public_output_dir=tmp_run,
            private_context_path=priv_path,
            seed=1,
            blinding_key=FIXED_KEY,
        )
    # Public run dir should not have been newly populated beyond original state
    contents = os.listdir(tmp_run)
    assert "manifest.json" not in contents, "Partial manifest found after failure"


def test_preparation_failure_no_partial_private_context():
    """Req #28: Failed preparation must not leave partial private context."""
    # Force failure: private context path inside public run (rejected before staging)
    tmp = tempfile.mkdtemp()
    priv_path = os.path.join(tmp, "private_context.json")

    with pytest.raises(ValueError):
        prepare_benchmark_run(
            public_output_dir=tmp,
            private_context_path=priv_path,
            seed=1,
            blinding_key=FIXED_KEY,
        )
    assert not os.path.exists(priv_path), "Partial private context found after failure"


# ---------------------------------------------------------------------------
# Pre-existing tests updated for new API
# ---------------------------------------------------------------------------


def test_three_arms_generated():
    run_dir, priv_path, manifest, _ = _prepare_run()
    arms = manifest["arms"]
    assert set(arms) == {"standard_review", "strong_protocol", "epistemic_workflow"}


def test_packet_dirs_exist():
    run_dir, priv_path, manifest, _ = _prepare_run()
    for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
        arm_dir = os.path.join(run_dir, "packets", arm)
        assert os.path.isdir(arm_dir), f"Missing arm dir: {arm}"


def test_18_packets_per_arm():
    run_dir, priv_path, manifest, _ = _prepare_run()
    for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
        arm_dir = os.path.join(run_dir, "packets", arm)
        packets = [f for f in os.listdir(arm_dir) if f.endswith(".json")]
        assert len(packets) == 18, f"arm={arm}: expected 18 packets, got {len(packets)}"


def test_common_materials_hash_equal_across_arms():
    """All three arms for the same case must have the same common_materials_sha256."""
    run_dir, priv_path, manifest, _ = _prepare_run()
    with open(priv_path, "r") as f:
        ctx = json.load(f)

    # Build alias -> common_sha from manifest
    alias_sha = {p["case_alias"]: p["common_materials_sha256"] for p in manifest["packets"]}

    # Group by case_id using private context
    case_shas: Dict[str, set] = {}
    for b in ctx["alias_bindings"]:
        cid = b["case_id"]
        alias = b["case_alias"]
        sha = alias_sha.get(alias)
        if sha:
            if cid not in case_shas:
                case_shas[cid] = set()
            case_shas[cid].add(sha)

    for case_id, shas in case_shas.items():
        assert len(shas) == 1, f"{case_id}: common_materials_sha256 differs across arms: {shas}"


def test_no_oracle_leakage_in_packets():
    run_dir, priv_path, manifest, _ = _prepare_run()
    for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
        arm_dir = os.path.join(run_dir, "packets", arm)
        for fname in os.listdir(arm_dir):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(arm_dir, fname), "r", encoding="utf-8") as f:
                packet = json.load(f)
            leaks = scan_packet_for_oracle_leakage(packet)
            assert not leaks, f"Oracle leakage in {arm}/{fname}: {leaks}"


def test_no_real_case_id_in_packet_json():
    run_dir, priv_path, manifest, _ = _prepare_run()
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


def test_all_packet_hashes_valid():
    run_dir, priv_path, manifest, _ = _prepare_run()
    for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
        arm_dir = os.path.join(run_dir, "packets", arm)
        for fname in os.listdir(arm_dir):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(arm_dir, fname), "r", encoding="utf-8") as f:
                packet = json.load(f)
            errors = validate_packet(packet)
            assert not errors, f"Packet validation errors in {arm}/{fname}: {errors}"


def test_generate_case_alias_deterministic():
    key = FIXED_KEY
    a1 = generate_case_alias("BRN-TEST", "standard_review", "EBR-001", key)
    a2 = generate_case_alias("BRN-TEST", "standard_review", "EBR-001", key)
    assert a1 == a2


def test_generate_case_alias_differs_by_arm():
    key = FIXED_KEY
    a_alias = generate_case_alias("BRN-TEST", "standard_review", "EBR-001", key)
    b_alias = generate_case_alias("BRN-TEST", "strong_protocol", "EBR-001", key)
    c_alias = generate_case_alias("BRN-TEST", "epistemic_workflow", "EBR-001", key)
    assert a_alias != b_alias
    assert b_alias != c_alias
    assert a_alias != c_alias


def test_validate_public_run_integrity_passes_on_valid_run():
    run_dir, priv_path, manifest, _ = _prepare_run()
    ok, errors = validate_public_run_integrity(run_dir)
    assert ok, f"Public run integrity failed: {errors}"


def test_validate_private_scoring_context_passes_on_valid():
    run_dir, priv_path, manifest, _ = _prepare_run()
    ok, errors = validate_private_scoring_context(run_dir, priv_path)
    assert ok, f"Private context validation failed: {errors}"


def test_private_context_has_oracle_corpus_sha():
    run_dir, priv_path, manifest, _ = _prepare_run()
    with open(priv_path, "r") as f:
        ctx = json.load(f)
    assert "oracle_corpus_sha256" in ctx
    assert len(ctx["oracle_corpus_sha256"]) == 64


def test_private_context_has_alias_bindings_for_all_cases_all_arms():
    run_dir, priv_path, manifest, _ = _prepare_run()
    with open(priv_path, "r") as f:
        ctx = json.load(f)
    bindings = ctx["alias_bindings"]
    expected_count = len(REQUIRED_CASE_IDS) * len(list(BenchmarkArm))
    assert len(bindings) == expected_count, (
        f"Expected {expected_count} bindings, got {len(bindings)}"
    )


def test_manifest_has_correct_exact_keys():
    run_dir, priv_path, manifest, _ = _prepare_run()
    assert set(manifest.keys()) == PUBLIC_MANIFEST_EXACT_KEYS


def test_manifest_case_count():
    run_dir, priv_path, manifest, _ = _prepare_run()
    assert manifest["case_count"] == 18


def test_manifest_run_manifest_sha256_valid():
    run_dir, priv_path, manifest, _ = _prepare_run()
    stored = manifest.get("run_manifest_sha256", "")
    body = {k: v for k, v in manifest.items() if k != "run_manifest_sha256"}
    expected = compute_canonical_sha256(body)
    assert stored == expected, "Manifest self-hash mismatch"


def test_strong_protocol_checklist_has_14_items():
    assert len(STRONG_PROTOCOL_CHECKLIST) == 14
