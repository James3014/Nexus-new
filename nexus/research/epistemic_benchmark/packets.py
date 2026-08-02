"""
Epistemic Workflow Benchmark v0 — Packet Preparation.

Generates three fair arm packets from public corpus cases.
Oracle fields are never included in packets.
Case aliases use HMAC-SHA256 with a private blinding key — cannot be reversed
without the key, even with the public seed.
"""

import hashlib
import hmac
import json
import os
import secrets
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from nexus.research.epistemic_benchmark.contracts import (
    BENCHMARK_PACKET_SCHEMA,
    BENCHMARK_PRIVATE_CONTEXT_SCHEMA,
    BENCHMARK_PUBLIC_MANIFEST_SCHEMA,
    PRIVATE_CONTEXT_EXACT_KEYS,
    PUBLIC_MANIFEST_EXACT_KEYS,
    PUBLIC_MANIFEST_FORBIDDEN_KEYS,
    PUBLIC_MANIFEST_PACKET_EXACT_KEYS,
    BenchmarkArm,
    compute_canonical_sha256,
    validate_packet,
    validate_sha256,
)
from nexus.research.epistemic_benchmark.corpus import (
    REQUIRED_CASE_IDS,
    get_all_oracles,
    get_public_corpus,
    get_corpus_version,
)

# ---------------------------------------------------------------------------
# Strong Protocol Checklist (versioned)
# ---------------------------------------------------------------------------

STRONG_PROTOCOL_VERSION = "STRONG_PROTOCOL_V1"

STRONG_PROTOCOL_CHECKLIST: List[str] = [
    "1. Verify that the candidate identity exactly matches the task contract specification.",
    "2. Verify that all mandatory checks listed in the task contract were actually executed (not just claimed).",
    "3. Distinguish between test executions and unique test identifiers — repeated execution of the same test does not count as additional test coverage.",
    "4. Check for any skipped, excluded, or unverified scope; any exclusion must be explicitly disclosed and justified.",
    "5. Verify that the verifier or review tool operated in read-only mode and did not modify any state during verification.",
    "6. Verify artifact binding: the artifact hash must match the sealed commitment and refer to the correct version.",
    "7. Check all cross-run references: evidence must be bound to the declared run, not borrowed from other runs.",
    "8. Check all cross-claim references: evidence must be directly bound to the evaluated claim, not reused from other claims.",
    "9. Detect valid-hash semantic mismatch: a cryptographically valid hash that refers to the wrong version or content is still a binding failure.",
    "10. Check authority unlock: verify that any public claim, integration approval, or production readiness declaration is supported by proper authority grants.",
    "11. Actively search for negative controls and contradicting evidence; do not rely solely on affirmative evidence.",
    "12. If evidence is insufficient to reach a ACCEPT or REJECT decision with confidence, return BLOCK — do not force a binary decision.",
    "13. Do not treat fluent narrative or confident language as evidence; only cited, verifiable material counts.",
    "14. State the maximum supportable claim given the available evidence — do not overstate what the evidence shows.",
]

# Arm-specific overlays
ARM_A_OVERLAY: Dict[str, Any] = {
    "review_instruction": (
        "Independently review the candidate using the provided materials and evidence. "
        "Return your decision as ACCEPT, REJECT, or BLOCK. "
        "Cite the specific evidence references that support your decision. "
        "If the available evidence is insufficient for a confident decision, return BLOCK."
    ),
}

ARM_B_OVERLAY: Dict[str, Any] = {
    "protocol": STRONG_PROTOCOL_VERSION,
    "checklist": STRONG_PROTOCOL_CHECKLIST,
}

# Arm C has Strong Protocol checklist (IDENTICAL to Arm B) PLUS epistemic_structure
# The epistemic_structure is populated per-case from the corpus epistemic_projection.
# ARM_C_OVERLAY is not a constant — it is built per-case in _build_arm_c_overlay.

# ---------------------------------------------------------------------------
# Forbidden strings in public packets (oracle leakage detection)
# ---------------------------------------------------------------------------

ORACLE_FORBIDDEN_STRINGS: Tuple[str, ...] = (
    "oracle_class", "oracle_decision", "CLEAN", "DEFECTIVE", "INDETERMINATE",
    "known_defects", "required_detection", "oracle_sha256",
    "EBR-001-D", "EBR-002-D", "EBR-003-D", "EBR-004-D", "EBR-005-D",
    "EBR-006-D", "EBR-007-D", "EBR-008-D", "EBR-009-D", "EBR-010-D",
    "EBR-011-D", "EBR-012-D", "EBR-013-D", "EBR-014-D", "EBR-015-D",
)

# Strings that must not directly appear as case IDs in packets
REAL_CASE_IDS: Set[str] = set(REQUIRED_CASE_IDS)


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Secret-key HMAC alias generation
# ---------------------------------------------------------------------------

def generate_case_alias(
    benchmark_run_id: str,
    arm: str,
    case_id: str,
    blinding_key: bytes,
) -> str:
    """
    Deterministically generate a case alias using HMAC-SHA256 with a secret blinding key.

    Properties:
    - Same key/run/arm/case → same alias (deterministic).
    - Different arm → different alias (isolation).
    - Different key → different alias (key dependency).
    - Cannot be reversed without the blinding_key.
    - The seed does NOT appear in the HMAC key or message.
    """
    if not isinstance(blinding_key, bytes) or len(blinding_key) != 32:
        raise ValueError("blinding_key must be exactly 32 bytes")
    message = f"{benchmark_run_id}:{arm}:{case_id}".encode("utf-8")
    digest = hmac.new(
        key=blinding_key,
        msg=message,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"CASE-{digest[:16].upper()}"


# ---------------------------------------------------------------------------
# Common materials hash
# ---------------------------------------------------------------------------

def compute_common_materials_sha256(case: Dict[str, Any]) -> str:
    """
    Hash of the materials that are identical across all arms.
    Covers: task_contract, candidate_summary, materials, available_evidence_refs, response_contract.
    """
    common = {
        "task_contract": case["task_contract"],
        "candidate_summary": case["candidate_summary"],
        "materials": case["materials"],
        "available_evidence_refs": case["available_evidence_refs"],
        "response_contract": case["response_contract"],
    }
    return _sha256(_canonical_json(common))


# ---------------------------------------------------------------------------
# Arm C overlay builder (case-specific epistemic_structure)
# ---------------------------------------------------------------------------

def _build_arm_c_overlay(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build Arm C overlay: same STRONG_PROTOCOL checklist as Arm B,
    plus case-specific epistemic_structure from the corpus epistemic_projection.
    The epistemic_structure is a structured dict, not generic strings.
    """
    projection = case.get("epistemic_projection", {})
    # Extract structured data from projection (no free prose, no oracle info)
    epistemic_structure = {
        "object_bindings": projection.get("object_bindings", []),
        "source_lineage": projection.get("source_lineage", []),
        "extraction_assessment_separation": projection.get("extraction_assessment_separation", []),
        "verification_status": projection.get("verification_status", []),
        "cannot_establish_flags": projection.get("cannot_establish_flags", []),
        "conflicts": projection.get("conflicts", []),
        "authority_locks": projection.get("authority_locks", {}),
        "review_report": projection.get("review_report", {}),
    }
    return {
        "protocol": STRONG_PROTOCOL_VERSION,
        "checklist": STRONG_PROTOCOL_CHECKLIST,
        "epistemic_structure": epistemic_structure,
    }


# ---------------------------------------------------------------------------
# Packet builder
# ---------------------------------------------------------------------------

def _build_packet(
    benchmark_run_id: str,
    arm: BenchmarkArm,
    arm_protocol_version: str,
    case_alias: str,
    case: Dict[str, Any],
    arm_overlay: Dict[str, Any],
    common_materials_sha256: str,
) -> Dict[str, Any]:
    common_materials = {
        "task_contract": case["task_contract"],
        "candidate_summary": case["candidate_summary"],
        "materials": case["materials"],
        "available_evidence_refs": case["available_evidence_refs"],
    }

    body = {
        "schema": BENCHMARK_PACKET_SCHEMA,
        "benchmark_run_id": benchmark_run_id,
        "arm": arm.value,
        "arm_protocol_version": arm_protocol_version,
        "case_alias": case_alias,
        "case_version": case["case_version"],
        "common_materials": common_materials,
        "common_materials_sha256": common_materials_sha256,
        "arm_overlay": arm_overlay,
        "response_contract": case["response_contract"],
    }
    body["packet_sha256"] = compute_canonical_sha256(body)
    return body


# ---------------------------------------------------------------------------
# Leakage scanner
# ---------------------------------------------------------------------------

def scan_packet_for_oracle_leakage(packet: Dict[str, Any]) -> List[str]:
    """
    Scan a packet for any oracle information or real case IDs.
    Returns list of leakage violations.
    """
    leaks: List[str] = []
    packet_str = _canonical_json(packet)

    # Check for forbidden oracle strings
    for forbidden in ORACLE_FORBIDDEN_STRINGS:
        if forbidden in packet_str:
            leaks.append(f"ORACLE_LEAKAGE_STRING: {forbidden!r}")

    # Check that real case IDs do not appear in packet
    for case_id in REAL_CASE_IDS:
        if f'"{case_id}"' in packet_str:
            leaks.append(f"ORACLE_LEAKAGE_CASE_ID: {case_id!r}")

    return leaks


# ---------------------------------------------------------------------------
# Public manifest builder
# ---------------------------------------------------------------------------

def _build_public_manifest(
    benchmark_run_id: str,
    corpus_version: str,
    created_at: str,
    arms: List[str],
    case_count: int,
    packets_list: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build the public manifest. Does NOT include seed, case IDs, or alias→case maps.
    packets_list: sorted list of {arm, case_alias, relative_path, packet_sha256, common_materials_sha256}
    """
    body = {
        "schema": BENCHMARK_PUBLIC_MANIFEST_SCHEMA,
        "benchmark_run_id": benchmark_run_id,
        "corpus_version": corpus_version,
        "created_at": created_at,
        "arms": arms,
        "case_count": case_count,
        "packets": sorted(packets_list, key=lambda p: (p["arm"], p["case_alias"])),
    }
    # Verify no forbidden keys leaked
    body_str = _canonical_json(body)
    for fk in PUBLIC_MANIFEST_FORBIDDEN_KEYS:
        if f'"{fk}"' in body_str and fk in body:
            raise ValueError(f"MANIFEST_FORBIDDEN_KEY_LEAKED: {fk}")
    body["run_manifest_sha256"] = compute_canonical_sha256(
        {k: v for k, v in body.items() if k != "run_manifest_sha256"}
    )
    return body


# ---------------------------------------------------------------------------
# Private context builder
# ---------------------------------------------------------------------------

def _build_private_context(
    benchmark_run_id: str,
    corpus_version: str,
    seed: int,
    blinding_key: bytes,
    alias_bindings: List[Dict[str, str]],
    oracle_corpus_sha256: str,
    public_manifest_sha256: str,
) -> Dict[str, Any]:
    body = {
        "schema": BENCHMARK_PRIVATE_CONTEXT_SCHEMA,
        "benchmark_run_id": benchmark_run_id,
        "corpus_version": corpus_version,
        "seed": seed,
        "blinding_key_hex": blinding_key.hex(),
        "alias_bindings": sorted(
            alias_bindings, key=lambda b: (b["arm"], b["case_alias"])
        ),
        "oracle_corpus_sha256": oracle_corpus_sha256,
        "public_manifest_sha256": public_manifest_sha256,
    }
    body["private_context_sha256"] = compute_canonical_sha256(
        {k: v for k, v in body.items() if k != "private_context_sha256"}
    )
    return body


# ---------------------------------------------------------------------------
# Main run preparation
# ---------------------------------------------------------------------------

def prepare_benchmark_run(
    public_output_dir: Optional[str] = None,
    private_context_path: Optional[str] = None,
    seed: int = 0,
    corpus_version: str = "v0",
    *,
    blinding_key: Optional[bytes] = None,
    created_at: Optional[str] = None,
    # Legacy compat: output_dir is deprecated, use public_output_dir
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Prepare a full benchmark run: public manifest + packets for all 3 arms
    + private context with alias bindings and oracle commitment.

    Oracle is NEVER written to the output directory.
    Seed is NEVER written to the public manifest or packets.
    Blinding key is NEVER written to logs or stdout.

    Returns the public manifest.
    """
    import datetime

    # Legacy compat: if called with old kwarg signature
    if output_dir is not None and public_output_dir is None:
        public_output_dir = output_dir

    # Require public_output_dir
    if public_output_dir is None:
        raise ValueError("public_output_dir is required")

    # Legacy compat: auto-derive private_context_path if not provided
    # Place it as a sibling of the public run directory to satisfy the
    # "outside public run" constraint. Legacy callers (observations/metrics/
    # report tests) do not need to inspect the private context.
    if private_context_path is None:
        _pub_parent = os.path.dirname(os.path.abspath(public_output_dir))
        _pub_name = os.path.basename(os.path.abspath(public_output_dir))
        private_context_path = os.path.join(
            _pub_parent, f"_{_pub_name}_private_context.json"
        )

    if created_at is None:
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Generate blinding key
    if blinding_key is None:
        blinding_key = secrets.token_bytes(32)
    if not isinstance(blinding_key, bytes) or len(blinding_key) != 32:
        raise ValueError("blinding_key must be exactly 32 bytes")

    # Safety: private_context_path must not be inside public_output_dir
    pub_abs = os.path.realpath(os.path.abspath(public_output_dir))
    priv_abs = os.path.realpath(os.path.abspath(private_context_path))
    if priv_abs.startswith(pub_abs + os.sep) or priv_abs == pub_abs:
        raise ValueError(
            f"PRIVATE_CONTEXT_INSIDE_PUBLIC_RUN: private_context_path must be outside public_output_dir"
        )

    # Fail closed: public output must not exist or must be empty
    if os.path.exists(public_output_dir):
        existing = os.listdir(public_output_dir) if os.path.isdir(public_output_dir) else ["?"]
        if existing:
            raise FileExistsError(
                f"PUBLIC_OUTPUT_NOT_EMPTY: {public_output_dir!r} already exists and is non-empty"
            )

    # Fail closed: private context must not exist
    if os.path.exists(private_context_path):
        raise FileExistsError(
            f"PRIVATE_CONTEXT_EXISTS: {private_context_path!r} already exists"
        )

    # Deterministic benchmark_run_id from seed + corpus_version
    run_id_material = f"benchmark:{corpus_version}:{seed}"
    benchmark_run_id = f"BRN-{_sha256(run_id_material)[:12].upper()}"

    cases = get_public_corpus()
    case_count = len(cases)
    oracles = get_all_oracles()

    # Compute oracle corpus sha256
    oracle_corpus_sha256 = compute_canonical_sha256(
        sorted([{k: v for k, v in o.items()} for o in oracles],
               key=lambda o: o.get("case_id", ""))
    )

    # Build packets and collect manifest data
    packets_list: List[Dict[str, Any]] = []
    alias_bindings: List[Dict[str, str]] = []

    # We'll stage files to a temp structure, then atomically move on success
    import tempfile, shutil
    staging_dir = tempfile.mkdtemp()
    staging_priv = private_context_path + ".staging_" + secrets.token_hex(8)

    try:
        # Create packet directories in staging
        for arm in BenchmarkArm:
            arm_dir = os.path.join(staging_dir, "packets", arm.value)
            os.makedirs(arm_dir, exist_ok=True)

        obs_dir = os.path.join(staging_dir, "observations")
        os.makedirs(obs_dir, exist_ok=True)
        for arm in BenchmarkArm:
            os.makedirs(os.path.join(obs_dir, arm.value), exist_ok=True)

        for case in cases:
            case_id = case["case_id"]
            common_sha = compute_common_materials_sha256(case)

            for arm in BenchmarkArm:
                alias = generate_case_alias(benchmark_run_id, arm.value, case_id, blinding_key)

                if arm == BenchmarkArm.STANDARD_REVIEW:
                    overlay = ARM_A_OVERLAY
                    protocol_version = "STANDARD_REVIEW_V1"
                elif arm == BenchmarkArm.STRONG_PROTOCOL:
                    overlay = ARM_B_OVERLAY
                    protocol_version = STRONG_PROTOCOL_VERSION
                else:  # EPISTEMIC_WORKFLOW
                    overlay = _build_arm_c_overlay(case)
                    protocol_version = STRONG_PROTOCOL_VERSION

                packet = _build_packet(
                    benchmark_run_id=benchmark_run_id,
                    arm=arm,
                    arm_protocol_version=protocol_version,
                    case_alias=alias,
                    case=case,
                    arm_overlay=overlay,
                    common_materials_sha256=common_sha,
                )

                # Verify no oracle leakage
                leaks = scan_packet_for_oracle_leakage(packet)
                if leaks:
                    raise ValueError(f"Oracle leakage detected in packet for {case_id}/{arm.value}: {leaks}")

                # Validate packet
                errors = validate_packet(packet)
                if errors:
                    raise ValueError(f"Packet validation failed for {case_id}/{arm.value}: {errors}")

                # Write packet to staging
                packet_filename = f"{alias}.json"
                relative_path = f"packets/{arm.value}/{packet_filename}"
                packet_path = os.path.join(staging_dir, relative_path)
                _atomic_write_json(packet, packet_path)

                packets_list.append({
                    "arm": arm.value,
                    "case_alias": alias,
                    "relative_path": relative_path,
                    "packet_sha256": packet["packet_sha256"],
                    "common_materials_sha256": common_sha,
                })
                alias_bindings.append({
                    "arm": arm.value,
                    "case_alias": alias,
                    "case_id": case_id,
                })

        # Build public manifest (no seed, no case IDs)
        manifest = _build_public_manifest(
            benchmark_run_id=benchmark_run_id,
            corpus_version=corpus_version,
            created_at=created_at,
            arms=[arm.value for arm in BenchmarkArm],
            case_count=case_count,
            packets_list=packets_list,
        )

        # Write manifest to staging
        manifest_path = os.path.join(staging_dir, "manifest.json")
        _atomic_write_json(manifest, manifest_path)

        # Build private context
        private_ctx = _build_private_context(
            benchmark_run_id=benchmark_run_id,
            corpus_version=corpus_version,
            seed=seed,
            blinding_key=blinding_key,
            alias_bindings=alias_bindings,
            oracle_corpus_sha256=oracle_corpus_sha256,
            public_manifest_sha256=manifest["run_manifest_sha256"],
        )

        # Write private context to staging location
        priv_dir = os.path.dirname(staging_priv)
        if priv_dir:
            os.makedirs(priv_dir, exist_ok=True)
        _atomic_write_json(private_ctx, staging_priv)

        # Atomic promotion: move staging to final locations
        # Move public run. If public_output_dir already exists (e.g. from
        # mkdtemp in tests) but is empty, shutil.move would move staging
        # INSIDE it rather than replacing it. Remove the empty dir first.
        pub_abs_final = os.path.abspath(public_output_dir)
        if os.path.isdir(pub_abs_final):
            try:
                os.rmdir(pub_abs_final)  # only succeeds if empty
            except OSError:
                pass  # non-empty: already guarded above
        os.rename(staging_dir, pub_abs_final)
        staging_dir = None  # prevent cleanup

        # Move private context
        priv_final_dir = os.path.dirname(os.path.abspath(private_context_path))
        if priv_final_dir:
            os.makedirs(priv_final_dir, exist_ok=True)
        os.replace(staging_priv, private_context_path)
        staging_priv = None  # prevent cleanup

    except Exception:
        # Cleanup: do not leave partial artifacts
        if staging_dir is not None and os.path.exists(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)
        if staging_priv is not None and os.path.exists(staging_priv):
            try:
                os.unlink(staging_priv)
            except OSError:
                pass
        raise

    return manifest


# ---------------------------------------------------------------------------
# Public Run Integrity Validator
# ---------------------------------------------------------------------------

def validate_public_run_integrity(
    public_run_dir: str,
) -> Tuple[bool, List[str]]:
    """
    Validate the integrity of a public benchmark run directory.

    Checks:
    1. Manifest exists.
    2. Manifest exact keys.
    3. Manifest self-hash.
    4. Packet inventory exact (no missing, no extra).
    5. Packet relative path safety.
    6. Packet exact keys.
    7. Packet self-hash.
    8. Packet hash == manifest commitment.
    9. Packet arm/alias == manifest.
    10. Common materials hash == manifest.
    11. Each arm packet count == case_count.
    12. Alias globally unique.
    13. No private context, oracle, seed, or case map in public tree.
    """
    from nexus.research.epistemic_benchmark.contracts import (
        PUBLIC_MANIFEST_EXACT_KEYS, PUBLIC_MANIFEST_PACKET_EXACT_KEYS,
        PACKET_EXACT_KEYS, PACKET_FORBIDDEN_KEYS,
    )

    errors: List[str] = []

    # 1. Manifest exists
    manifest_path = os.path.join(public_run_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        errors.append("BENCHMARK_MANIFEST_MISSING")
        return False, errors

    # Load manifest
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        errors.append(f"BENCHMARK_MANIFEST_LOAD_ERROR: {e}")
        return False, errors

    # 2. Manifest exact keys
    mkeys = set(manifest.keys())
    missing_mk = PUBLIC_MANIFEST_EXACT_KEYS - mkeys
    extra_mk = mkeys - PUBLIC_MANIFEST_EXACT_KEYS
    if missing_mk:
        errors.append(f"BENCHMARK_MANIFEST_MISSING_KEYS: {sorted(missing_mk)}")
    if extra_mk:
        errors.append(f"BENCHMARK_MANIFEST_EXTRA_KEYS: {sorted(extra_mk)}")

    # Check no forbidden keys in manifest
    from nexus.research.epistemic_benchmark.contracts import PUBLIC_MANIFEST_FORBIDDEN_KEYS
    for fk in PUBLIC_MANIFEST_FORBIDDEN_KEYS:
        if fk in manifest:
            errors.append(f"BENCHMARK_PUBLIC_ORACLE_LEAK: manifest contains forbidden key {fk!r}")

    # 3. Manifest self-hash
    stored_hash = manifest.get("run_manifest_sha256", "")
    body = {k: v for k, v in manifest.items() if k != "run_manifest_sha256"}
    expected_hash = compute_canonical_sha256(body)
    if stored_hash != expected_hash:
        errors.append("BENCHMARK_MANIFEST_HASH_MISMATCH")

    # Collect expected packets from manifest
    expected_packets = manifest.get("packets", [])
    case_count = manifest.get("case_count", 0)
    expected_arms = manifest.get("arms", [])

    # 4. Packet inventory: build expected file set
    expected_rel_paths: Set[str] = set()
    manifest_by_rel: Dict[str, Dict[str, Any]] = {}
    seen_aliases: List[str] = []

    for pkt_entry in expected_packets:
        # Packet entry keys
        pkt_entry_keys = set(pkt_entry.keys())
        missing_pek = PUBLIC_MANIFEST_PACKET_EXACT_KEYS - pkt_entry_keys
        extra_pek = pkt_entry_keys - PUBLIC_MANIFEST_PACKET_EXACT_KEYS
        if missing_pek:
            errors.append(f"BENCHMARK_MANIFEST_PACKET_MISSING_KEYS: {sorted(missing_pek)}")
        if extra_pek:
            errors.append(f"BENCHMARK_MANIFEST_PACKET_EXTRA_KEYS: {sorted(extra_pek)}")

        rel = pkt_entry.get("relative_path", "")

        # 7. Packet relative path safety
        if not rel:
            errors.append("BENCHMARK_PACKET_PATH_INVALID: empty relative_path")
        elif os.path.isabs(rel):
            errors.append(f"BENCHMARK_PACKET_PATH_INVALID: absolute path {rel!r}")
        elif ".." in rel.split("/"):
            errors.append(f"BENCHMARK_PACKET_PATH_INVALID: traversal in {rel!r}")
        elif not rel.startswith("packets/"):
            errors.append(f"BENCHMARK_PACKET_PATH_INVALID: not under packets/ {rel!r}")
        else:
            expected_rel_paths.add(rel)
            manifest_by_rel[rel] = pkt_entry

        alias = pkt_entry.get("case_alias", "")
        seen_aliases.append(alias)

    # 14. Alias globally unique
    if len(seen_aliases) != len(set(seen_aliases)):
        from collections import Counter
        dups = [a for a, c in Counter(seen_aliases).items() if c > 1]
        errors.append(f"BENCHMARK_ALIAS_NOT_UNIQUE: duplicates={dups}")

    # 5. Walk actual packet files
    actual_rel_paths: Set[str] = set()
    packets_root = os.path.join(public_run_dir, "packets")
    if os.path.isdir(packets_root):
        for arm_name in os.listdir(packets_root):
            arm_dir = os.path.join(packets_root, arm_name)
            if not os.path.isdir(arm_dir):
                continue
            for fname in os.listdir(arm_dir):
                if fname.endswith(".json"):
                    actual_rel_paths.add(f"packets/{arm_name}/{fname}")

    missing_packets = expected_rel_paths - actual_rel_paths
    extra_packets = actual_rel_paths - expected_rel_paths
    for mp in sorted(missing_packets):
        errors.append(f"BENCHMARK_PACKET_MISSING: {mp}")
    for ep in sorted(extra_packets):
        errors.append(f"BENCHMARK_PACKET_UNEXPECTED: {ep}")

    # 6+8+9+10+11. Validate each packet
    from nexus.research.epistemic_benchmark.contracts import PACKET_EXACT_KEYS, PACKET_FORBIDDEN_KEYS
    for rel, entry in manifest_by_rel.items():
        pkt_path = os.path.join(public_run_dir, rel)
        if not os.path.exists(pkt_path):
            continue  # already reported as missing

        try:
            with open(pkt_path, "r", encoding="utf-8") as f:
                packet = json.load(f)
        except Exception as e:
            errors.append(f"BENCHMARK_PACKET_LOAD_ERROR: {rel}: {e}")
            continue

        # 8. Packet exact keys
        pkt_keys = set(packet.keys())
        missing_pk = PACKET_EXACT_KEYS - pkt_keys
        extra_pk = pkt_keys - PACKET_EXACT_KEYS
        if missing_pk:
            errors.append(f"BENCHMARK_PACKET_MISSING_KEYS: {rel}: {sorted(missing_pk)}")
        if extra_pk:
            errors.append(f"BENCHMARK_PACKET_EXTRA_KEYS: {rel}: {sorted(extra_pk)}")

        leaked_pk = PACKET_FORBIDDEN_KEYS & pkt_keys
        if leaked_pk:
            errors.append(f"BENCHMARK_PUBLIC_ORACLE_LEAK: {rel}: forbidden keys {sorted(leaked_pk)}")

        # 9. Packet self-hash
        stored_psha = packet.get("packet_sha256", "")
        pbody = {k: v for k, v in packet.items() if k != "packet_sha256"}
        expected_psha = compute_canonical_sha256(pbody)
        if stored_psha != expected_psha:
            errors.append(f"BENCHMARK_PACKET_HASH_MISMATCH: {rel}")

        # 10. Packet hash == manifest commitment
        manifest_psha = entry.get("packet_sha256", "")
        if stored_psha != manifest_psha:
            errors.append(f"BENCHMARK_PACKET_HASH_MISMATCH: {rel}: packet_sha256 differs from manifest")

        # 11. Packet arm/alias == manifest
        if packet.get("arm") != entry.get("arm"):
            errors.append(f"BENCHMARK_PACKET_BINDING_MISMATCH: {rel}: arm mismatch")
        if packet.get("case_alias") != entry.get("case_alias"):
            errors.append(f"BENCHMARK_PACKET_BINDING_MISMATCH: {rel}: case_alias mismatch")

        # 12. Common materials hash == manifest
        if packet.get("common_materials_sha256") != entry.get("common_materials_sha256"):
            errors.append(f"BENCHMARK_PACKET_BINDING_MISMATCH: {rel}: common_materials_sha256 mismatch")

    # 13. Each arm packet count == case_count
    if case_count > 0 and expected_arms:
        arm_counts: Dict[str, int] = {}
        for pkt_entry in expected_packets:
            arm = pkt_entry.get("arm", "")
            arm_counts[arm] = arm_counts.get(arm, 0) + 1
        for arm_name in expected_arms:
            cnt = arm_counts.get(arm_name, 0)
            if cnt != case_count:
                errors.append(
                    f"BENCHMARK_ARM_PACKET_COUNT_MISMATCH: arm={arm_name} got={cnt} expected={case_count}"
                )

    # 15. Check public tree for oracle/private artifacts
    _forbidden_artifact_names = (
        "oracle", "oracle_v0", "case_id_map", "expected_results",
        "answer_key", "private_context", "blinding_key",
    )
    for root, dirs, files in os.walk(public_run_dir):
        for fname in files:
            fname_lower = fname.lower()
            for fa in _forbidden_artifact_names:
                if fa in fname_lower and fname != "manifest.json":
                    errors.append(
                        f"BENCHMARK_PUBLIC_ORACLE_LEAK: forbidden artifact {fname!r} in {root!r}"
                    )
                    break

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Private Context Validator
# ---------------------------------------------------------------------------

def validate_private_scoring_context(
    public_run_dir: str,
    private_context_path: str,
) -> Tuple[bool, List[str]]:
    """
    Validate private scoring context against the public run.

    First calls validate_public_run_integrity(). Then validates:
    1. Private context exact keys.
    2. Private context self-hash.
    3. public_manifest_sha256 matches.
    4. oracle_corpus_sha256 matches canonical oracle.
    5. Alias bindings cover all public packets (no missing, no extra).
    6. Each case in three arms, exactly once.
    7. Unknown case ID rejected.
    8. Alias/arm consistent with public manifest.
    9. Private context not inside public run dir.
    """
    errors: List[str] = []

    # 9. Private context must not be inside public run
    pub_abs = os.path.realpath(os.path.abspath(public_run_dir))
    priv_abs = os.path.realpath(os.path.abspath(private_context_path))
    if priv_abs.startswith(pub_abs + os.sep) or priv_abs == pub_abs:
        errors.append("PRIVATE_CONTEXT_INSIDE_PUBLIC_RUN")
        return False, errors

    # Run public integrity check first
    pub_ok, pub_errors = validate_public_run_integrity(public_run_dir)
    if not pub_ok:
        errors.extend([f"PUBLIC_RUN_INVALID: {e}" for e in pub_errors])
        return False, errors

    # Load public manifest
    manifest_path = os.path.join(public_run_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Load private context
    if not os.path.exists(private_context_path):
        errors.append("PRIVATE_CONTEXT_MISSING")
        return False, errors

    try:
        with open(private_context_path, "r", encoding="utf-8") as f:
            ctx = json.load(f)
    except Exception as e:
        errors.append(f"PRIVATE_CONTEXT_LOAD_ERROR: {e}")
        return False, errors

    # 1. Private context exact keys
    ctx_keys = set(ctx.keys())
    missing_ck = PRIVATE_CONTEXT_EXACT_KEYS - ctx_keys
    extra_ck = ctx_keys - PRIVATE_CONTEXT_EXACT_KEYS
    if missing_ck:
        errors.append(f"PRIVATE_CONTEXT_MISSING_KEYS: {sorted(missing_ck)}")
    if extra_ck:
        errors.append(f"PRIVATE_CONTEXT_EXTRA_KEYS: {sorted(extra_ck)}")

    # 2. Private context self-hash
    stored_csha = ctx.get("private_context_sha256", "")
    cbody = {k: v for k, v in ctx.items() if k != "private_context_sha256"}
    expected_csha = compute_canonical_sha256(cbody)
    if stored_csha != expected_csha:
        errors.append("PRIVATE_CONTEXT_HASH_MISMATCH")

    # 3. public_manifest_sha256 matches
    manifest_sha = manifest.get("run_manifest_sha256", "")
    ctx_manifest_sha = ctx.get("public_manifest_sha256", "")
    if ctx_manifest_sha != manifest_sha:
        errors.append(
            f"PRIVATE_CONTEXT_MANIFEST_SHA_MISMATCH: ctx={ctx_manifest_sha!r} manifest={manifest_sha!r}"
        )

    # 4. oracle_corpus_sha256 matches canonical oracle
    from nexus.research.epistemic_benchmark.corpus import get_all_oracles
    oracles = get_all_oracles()
    expected_oracle_sha = compute_canonical_sha256(
        sorted([{k: v for k, v in o.items()} for o in oracles],
               key=lambda o: o.get("case_id", ""))
    )
    ctx_oracle_sha = ctx.get("oracle_corpus_sha256", "")
    if ctx_oracle_sha != expected_oracle_sha:
        errors.append(
            f"PRIVATE_CONTEXT_ORACLE_SHA_MISMATCH: ctx={ctx_oracle_sha!r} expected={expected_oracle_sha!r}"
        )

    # 5-8. Alias bindings coverage
    known_case_ids = set(REQUIRED_CASE_IDS)
    bindings = ctx.get("alias_bindings", [])

    # Build expected: {(arm, alias)} from public manifest packets
    expected_arm_aliases: Set[Tuple[str, str]] = set()
    for pkt in manifest.get("packets", []):
        arm = pkt.get("arm", "")
        alias = pkt.get("case_alias", "")
        expected_arm_aliases.add((arm, alias))

    actual_arm_aliases: Set[Tuple[str, str]] = set()
    case_arm_pairs: Set[Tuple[str, str]] = set()

    for b in bindings:
        arm = b.get("arm", "")
        alias = b.get("case_alias", "")
        case_id = b.get("case_id", "")

        # 7. Unknown case ID
        if case_id not in known_case_ids:
            errors.append(f"PRIVATE_CONTEXT_UNKNOWN_CASE_ID: {case_id!r}")

        actual_arm_aliases.add((arm, alias))
        case_arm_pairs.add((case_id, arm))

    # 5. Missing/extra bindings
    missing_bindings = expected_arm_aliases - actual_arm_aliases
    extra_bindings = actual_arm_aliases - expected_arm_aliases
    for mb in sorted(missing_bindings):
        errors.append(f"PRIVATE_CONTEXT_MISSING_BINDING: arm={mb[0]} alias={mb[1]}")
    for eb in sorted(extra_bindings):
        errors.append(f"PRIVATE_CONTEXT_EXTRA_BINDING: arm={eb[0]} alias={eb[1]}")

    # 6. Each case in three arms exactly once
    case_arm_counts: Dict[str, Set[str]] = {}
    for b in bindings:
        cid = b.get("case_id", "")
        arm = b.get("arm", "")
        if cid not in case_arm_counts:
            case_arm_counts[cid] = set()
        case_arm_counts[cid].add(arm)

    expected_arms_set = {arm.value for arm in BenchmarkArm}
    for cid, arms_seen in case_arm_counts.items():
        if cid in known_case_ids and arms_seen != expected_arms_set:
            missing_arms = expected_arms_set - arms_seen
            errors.append(
                f"PRIVATE_CONTEXT_CASE_ARM_COVERAGE_INCOMPLETE: case={cid} missing_arms={sorted(missing_arms)}"
            )

    # 8. Alias/arm consistent with public manifest
    # Build alias→entry from public manifest
    pub_alias_map: Dict[str, Dict[str, Any]] = {}
    for pkt in manifest.get("packets", []):
        alias = pkt.get("case_alias", "")
        pub_alias_map[alias] = pkt

    for b in bindings:
        alias = b.get("case_alias", "")
        arm = b.get("arm", "")
        if alias in pub_alias_map:
            pub_arm = pub_alias_map[alias].get("arm", "")
            if pub_arm != arm:
                errors.append(
                    f"PRIVATE_CONTEXT_ARM_MISMATCH: alias={alias!r} ctx_arm={arm!r} pub_arm={pub_arm!r}"
                )
        else:
            errors.append(f"PRIVATE_CONTEXT_ALIAS_NOT_IN_MANIFEST: alias={alias!r}")

    return len(errors) == 0, errors


def _atomic_write_json(obj: Any, path: str) -> None:
    import tempfile
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=dirname or ".", delete=False, suffix=".tmp"
    ) as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
        tmp_path = f.name
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Run directory accessors
# ---------------------------------------------------------------------------

def load_run_manifest(run_dir: str) -> Dict[str, Any]:
    """Load public manifest from run_dir.

    For backward compatibility with metrics/report code that expects
    packet_manifest and seed, this function also checks for a sibling
    private context file (created by prepare_benchmark_run in legacy mode).
    If found, injects packet_manifest ({case_id: {arm: alias}}) and seed
    into the returned dict. These fields are NOT written to manifest.json.
    """
    manifest_path = os.path.join(run_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"manifest.json not found in {run_dir}")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Backward-compat injection: try to load private context from sibling path
    # (the convention used when private_context_path was auto-derived)
    run_abs = os.path.abspath(run_dir)
    parent_dir = os.path.dirname(run_abs)
    run_name = os.path.basename(run_abs)
    sibling_priv_path = os.path.join(parent_dir, f"_{run_name}_private_context.json")
    if os.path.exists(sibling_priv_path):
        try:
            with open(sibling_priv_path, "r", encoding="utf-8") as f:
                priv = json.load(f)
            # Inject seed for report.py compat
            if "seed" not in manifest and "seed" in priv:
                manifest["seed"] = priv["seed"]
            # Inject packet_manifest for metrics.py compat
            # packet_manifest format: {case_id: {arm: alias}}
            if "packet_manifest" not in manifest:
                pm: Dict[str, Any] = {}
                for binding in priv.get("alias_bindings", []):
                    cid = binding.get("case_id", "")
                    arm = binding.get("arm", "")
                    alias = binding.get("case_alias", "")
                    if cid and arm and alias:
                        pm.setdefault(cid, {})[arm] = alias
                if pm:
                    manifest["packet_manifest"] = pm
        except Exception:
            pass  # If private context is unreadable, skip injection

    return manifest



def load_packet(run_dir: str, arm: str, alias: str) -> Dict[str, Any]:
    packet_path = os.path.join(run_dir, "packets", arm, f"{alias}.json")
    if not os.path.exists(packet_path):
        raise FileNotFoundError(f"Packet not found: {packet_path}")
    with open(packet_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_all_aliases(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Returns packets list from public manifest."""
    return manifest.get("packets", [])


def get_alias_to_case_map(private_context: Dict[str, Any]) -> Dict[str, str]:
    """Returns {alias: case_id} — PRIVATE: only used with private_context."""
    result: Dict[str, str] = {}
    for b in private_context.get("alias_bindings", []):
        alias = b.get("case_alias", "")
        case_id = b.get("case_id", "")
        if alias and case_id:
            result[alias] = case_id
    return result
