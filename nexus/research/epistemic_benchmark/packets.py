"""
Epistemic Workflow Benchmark v0 — Packet Preparation.

Generates three fair arm packets from public corpus cases.
Oracle fields are never included in packets.
Case aliases are deterministic but cannot be directly reversed to case IDs.
"""

import hashlib
import hmac
import json
import os
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from nexus.research.epistemic_benchmark.contracts import (
    BENCHMARK_PACKET_SCHEMA,
    BENCHMARK_RUN_SCHEMA,
    BenchmarkArm,
    compute_canonical_sha256,
    validate_packet,
)
from nexus.research.epistemic_benchmark.corpus import (
    REQUIRED_CASE_IDS,
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

# Arm C has Strong Protocol checklist PLUS epistemic structure — same checklist as Arm B
ARM_C_OVERLAY: Dict[str, Any] = {
    "protocol": STRONG_PROTOCOL_VERSION,
    "checklist": STRONG_PROTOCOL_CHECKLIST,
    "epistemic_structure": {
        "object_bindings": (
            "Verify object-level bindings: run_id, claim_id, artifact_id, "
            "assessment_id, and extraction_id must form a consistent chain."
        ),
        "source_lineage": (
            "Verify lineage independence of evidence sources. "
            "Derivative sources from the same parent do not provide independent support."
        ),
        "extraction_assessment_separation": (
            "Confirm that extraction (what was observed) is recorded separately "
            "from assessment (what it means for the claim)."
        ),
        "verification_status": (
            "Review the verification status fields: evidence_hash_status, "
            "evidence_seal_status, gate_a_status, evidence_pipeline_valid, "
            "claim_ledger_valid, adjudication_ledger_valid, decision_trace_valid."
        ),
        "cannot_establish_flags": (
            "For any assessment with direction=supports or direction=contradicts, "
            "verify that cannot_establish_present=true acknowledges epistemic limits."
        ),
        "conflicts": (
            "Identify any claims that have both supports and contradicts assessments. "
            "Conflicting evidence requires BLOCK unless one direction is clearly invalid."
        ),
        "authority_locks": (
            "Verify the ClaimBoundary authority locks: runtime_update_allowed, "
            "public_claim_allowed, public_benchmark_allowed, production_ready, "
            "integration_approved — all must be false unless properly unlocked."
        ),
        "review_report": (
            "If an Epistemic Review Report is provided, verify its hash, "
            "check source binding, and confirm it does not claim acceptance, "
            "proven status, or production readiness."
        ),
    },
}

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
# Deterministic case alias generation
# ---------------------------------------------------------------------------

def generate_case_alias(
    benchmark_run_id: str,
    arm: str,
    case_id: str,
    seed: int,
) -> str:
    """
    Deterministically generate a case alias that:
    - Is the same for the same inputs (deterministic).
    - Differs across arms for the same case (blind isolation).
    - Cannot be directly reversed to case_id without the seed.
    """
    key_material = f"{benchmark_run_id}:{arm}:{case_id}:{seed}".encode("utf-8")
    digest = hmac.new(
        key=str(seed).encode("utf-8"),
        msg=key_material,
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
        # Case ID must not appear as a value (key check only for technical fields)
        # We check in the JSON string but exclude the case_alias field format
        if f'"{case_id}"' in packet_str:
            leaks.append(f"ORACLE_LEAKAGE_CASE_ID: {case_id!r}")

    return leaks


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------

def _build_run_manifest(
    benchmark_run_id: str,
    corpus_version: str,
    seed: int,
    created_at: str,
    case_count: int,
    packet_manifest: Dict[str, Any],
) -> Dict[str, Any]:
    body = {
        "schema": BENCHMARK_RUN_SCHEMA,
        "benchmark_run_id": benchmark_run_id,
        "corpus_version": corpus_version,
        "seed": seed,
        "created_at": created_at,
        "arms": [arm.value for arm in BenchmarkArm],
        "case_count": case_count,
        "packet_manifest": packet_manifest,
    }
    body["run_manifest_sha256"] = compute_canonical_sha256(
        {k: v for k, v in body.items() if k != "run_manifest_sha256"}
    )
    return body


# ---------------------------------------------------------------------------
# Main run preparation
# ---------------------------------------------------------------------------

def prepare_benchmark_run(
    output_dir: str,
    seed: int,
    corpus_version: str = "v0",
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Prepare a full benchmark run: manifest + packets for all 3 arms.
    Oracle is NEVER written to the output directory.

    Returns the run manifest.
    """
    import datetime

    if created_at is None:
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Deterministic benchmark_run_id from seed + corpus_version
    run_id_material = f"benchmark:{corpus_version}:{seed}"
    benchmark_run_id = f"BRN-{_sha256(run_id_material)[:12].upper()}"

    cases = get_public_corpus()
    case_count = len(cases)

    # Create output directory structure
    run_dir = output_dir
    os.makedirs(run_dir, exist_ok=True)

    for arm in BenchmarkArm:
        arm_dir = os.path.join(run_dir, "packets", arm.value)
        os.makedirs(arm_dir, exist_ok=True)

    obs_dir = os.path.join(run_dir, "observations")
    os.makedirs(obs_dir, exist_ok=True)
    for arm in BenchmarkArm:
        os.makedirs(os.path.join(obs_dir, arm.value), exist_ok=True)

    packet_manifest: Dict[str, Any] = {}

    for case in cases:
        case_id = case["case_id"]
        common_sha = compute_common_materials_sha256(case)
        case_packets: Dict[str, str] = {}

        for arm in BenchmarkArm:
            alias = generate_case_alias(benchmark_run_id, arm.value, case_id, seed)

            if arm == BenchmarkArm.STANDARD_REVIEW:
                overlay = ARM_A_OVERLAY
                protocol_version = "STANDARD_REVIEW_V1"
            elif arm == BenchmarkArm.STRONG_PROTOCOL:
                overlay = ARM_B_OVERLAY
                protocol_version = STRONG_PROTOCOL_VERSION
            else:  # EPISTEMIC_WORKFLOW
                overlay = ARM_C_OVERLAY
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

            # Write packet
            packet_filename = f"{alias}.json"
            packet_path = os.path.join(run_dir, "packets", arm.value, packet_filename)
            _atomic_write_json(packet, packet_path)

            case_packets[arm.value] = alias

        packet_manifest[case_id] = case_packets

    # Build and write manifest (no oracle)
    manifest = _build_run_manifest(
        benchmark_run_id=benchmark_run_id,
        corpus_version=corpus_version,
        seed=seed,
        created_at=created_at,
        case_count=case_count,
        packet_manifest=packet_manifest,
    )

    manifest_path = os.path.join(run_dir, "manifest.json")
    _atomic_write_json(manifest, manifest_path)

    return manifest


def _atomic_write_json(obj: Any, path: str) -> None:
    import tempfile
    dirname = os.path.dirname(path)
    os.makedirs(dirname, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=dirname, delete=False, suffix=".tmp"
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
    manifest_path = os.path.join(run_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"manifest.json not found in {run_dir}")
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_packet(run_dir: str, arm: str, alias: str) -> Dict[str, Any]:
    packet_path = os.path.join(run_dir, "packets", arm, f"{alias}.json")
    if not os.path.exists(packet_path):
        raise FileNotFoundError(f"Packet not found: {packet_path}")
    with open(packet_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_all_aliases(manifest: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Returns {case_id: {arm: alias}} from manifest."""
    return manifest.get("packet_manifest", {})


def get_alias_to_case_map(manifest: Dict[str, Any]) -> Dict[str, str]:
    """Returns {alias: case_id} — PRIVATE: only used internally with oracle."""
    result: Dict[str, str] = {}
    for case_id, arms in manifest.get("packet_manifest", {}).items():
        for arm, alias in arms.items():
            result[alias] = case_id
    return result
