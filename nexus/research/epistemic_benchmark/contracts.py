"""
Epistemic Workflow Benchmark v0 — Contracts and Schema Definitions.

Closed enums, schema constants, and dataclass contracts.
All validation is strict: unknown values are rejected.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

BENCHMARK_CASE_SCHEMA = "nexus.epistemic_benchmark_case.v0"
BENCHMARK_ORACLE_SCHEMA = "nexus.epistemic_benchmark_oracle.v0"
BENCHMARK_ARM_SCHEMA = "nexus.epistemic_benchmark_arm.v0"
BENCHMARK_PACKET_SCHEMA = "nexus.epistemic_benchmark_packet.v0"
BENCHMARK_RUN_SCHEMA = "nexus.epistemic_benchmark_run.v0"
BENCHMARK_OBSERVATION_SCHEMA = "nexus.epistemic_benchmark_observation.v0"
BENCHMARK_REPORT_SCHEMA = "nexus.epistemic_benchmark_report.v0"

# ---------------------------------------------------------------------------
# Closed enums
# ---------------------------------------------------------------------------

class BenchmarkArm(str, Enum):
    STANDARD_REVIEW = "standard_review"
    STRONG_PROTOCOL = "strong_protocol"
    EPISTEMIC_WORKFLOW = "epistemic_workflow"


class BenchmarkDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    BLOCK = "BLOCK"


class OracleClass(str, Enum):
    CLEAN = "CLEAN"
    DEFECTIVE = "DEFECTIVE"
    INDETERMINATE = "INDETERMINATE"


class DefectSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Forbidden values that must never appear as status assertions
FORBIDDEN_TRUTH_STATUSES: Set[str] = {
    "TRUE", "FALSE", "PROVEN", "FINAL", "PRODUCTION_READY",
    "ARM_C_WINS", "LEDGER_PROVEN", "RESEARCH_IMPROVED",
    "STATISTICALLY_SIGNIFICANT",
}

# ---------------------------------------------------------------------------
# SHA-256 utilities
# ---------------------------------------------------------------------------

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_canonical_sha256(obj: Any) -> str:
    """Return SHA-256 of canonical JSON of obj."""
    return _sha256(_canonical_json(obj))


def validate_sha256(value: str) -> bool:
    return bool(value and _SHA256_HEX_RE.match(value))


# ---------------------------------------------------------------------------
# Case Material
# ---------------------------------------------------------------------------

CASE_MATERIAL_KEYS: Set[str] = {"ref", "type", "sha256", "content"}


def validate_case_material(m: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    keys = set(m.keys())
    if keys != CASE_MATERIAL_KEYS:
        errors.append(f"MATERIAL_KEYS_MISMATCH: got {sorted(keys)}")
    if not m.get("ref") or not isinstance(m.get("ref"), str):
        errors.append("MATERIAL_REF_MISSING")
    if not m.get("type") or not isinstance(m.get("type"), str):
        errors.append("MATERIAL_TYPE_MISSING")
    sha = m.get("sha256", "")
    if not validate_sha256(sha):
        errors.append(f"MATERIAL_SHA256_INVALID: {sha!r}")
    else:
        content = m.get("content", "")
        computed = _sha256(content if isinstance(content, str) else _canonical_json(content))
        if computed != sha:
            errors.append(f"MATERIAL_SHA256_MISMATCH: ref={m.get('ref')}")
    return errors


# ---------------------------------------------------------------------------
# Benchmark Case Contract
# ---------------------------------------------------------------------------

CASE_EXACT_KEYS: Set[str] = {
    "schema", "case_id", "case_version", "title_neutral", "task_contract",
    "candidate_summary", "materials", "available_evidence_refs",
    "response_contract", "public_case_sha256", "epistemic_projection",
}

# Keys that must NOT appear in public case
CASE_FORBIDDEN_KEYS: Set[str] = {
    "oracle", "oracle_class", "oracle_decision", "known_defects",
    "expected_answer", "required_detection", "defect_ids",
}


def validate_public_case(case: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    keys = set(case.keys())

    # Exact keys check
    missing = CASE_EXACT_KEYS - keys
    extra = keys - CASE_EXACT_KEYS
    if missing:
        errors.append(f"CASE_MISSING_KEYS: {sorted(missing)}")
    if extra:
        errors.append(f"CASE_EXTRA_KEYS: {sorted(extra)}")

    # Forbidden keys
    leaked = CASE_FORBIDDEN_KEYS & keys
    if leaked:
        errors.append(f"CASE_FORBIDDEN_KEYS: {sorted(leaked)}")

    # Required string fields
    for fld in ("case_id", "case_version", "title_neutral", "task_contract",
                "candidate_summary", "response_contract"):
        val = case.get(fld)
        if not val or not isinstance(val, str) or not val.strip():
            errors.append(f"CASE_FIELD_MISSING_OR_EMPTY: {fld}")

    # Materials
    materials = case.get("materials", [])
    if not isinstance(materials, list) or len(materials) < 2:
        errors.append("CASE_INSUFFICIENT_MATERIALS")
    else:
        refs = [m.get("ref") for m in materials]
        if refs != sorted(refs):
            errors.append("CASE_MATERIALS_NOT_SORTED")
        if len(set(refs)) != len(refs):
            errors.append("CASE_DUPLICATE_REFS")
        for m in materials:
            errors.extend(validate_case_material(m))

    # Evidence refs
    ev_refs = case.get("available_evidence_refs", [])
    if not isinstance(ev_refs, list) or len(ev_refs) < 1:
        errors.append("CASE_NO_EVIDENCE_REFS")

    # Hash
    sha = case.get("public_case_sha256", "")
    if not validate_sha256(sha):
        errors.append(f"CASE_SHA256_INVALID: {sha!r}")
    else:
        body = {k: v for k, v in case.items() if k != "public_case_sha256"}
        expected = compute_canonical_sha256(body)
        if expected != sha:
            errors.append("CASE_SHA256_MISMATCH")

    return errors


# ---------------------------------------------------------------------------
# Oracle Contract
# ---------------------------------------------------------------------------

ORACLE_EXACT_KEYS: Set[str] = {
    "schema", "case_id", "oracle_class", "oracle_decision",
    "known_defects", "indeterminate_reason", "oracle_sha256",
}

ORACLE_DEFECT_KEYS: Set[str] = {
    "defect_id", "severity", "category", "description",
    "required_detection", "supporting_public_refs",
}


def validate_oracle_record(oracle: Dict[str, Any], case: Optional[Dict[str, Any]] = None) -> List[str]:
    errors: List[str] = []
    keys = set(oracle.keys())

    missing = ORACLE_EXACT_KEYS - keys
    extra = keys - ORACLE_EXACT_KEYS
    if missing:
        errors.append(f"ORACLE_MISSING_KEYS: {sorted(missing)}")
    if extra:
        errors.append(f"ORACLE_EXTRA_KEYS: {sorted(extra)}")

    # Enum validation
    oc = oracle.get("oracle_class", "")
    if oc not in {e.value for e in OracleClass}:
        errors.append(f"ORACLE_CLASS_INVALID: {oc!r}")
    od = oracle.get("oracle_decision", "")
    if od not in {e.value for e in BenchmarkDecision}:
        errors.append(f"ORACLE_DECISION_INVALID: {od!r}")

    # Consistency: CLEAN→ACCEPT, DEFECTIVE→REJECT, INDETERMINATE→BLOCK
    expected_decision = {
        "CLEAN": "ACCEPT",
        "DEFECTIVE": "REJECT",
        "INDETERMINATE": "BLOCK",
    }.get(oc)
    if expected_decision and od != expected_decision:
        errors.append(f"ORACLE_DECISION_INCONSISTENT: class={oc} decision={od} expected={expected_decision}")

    # Defects
    defects = oracle.get("known_defects", [])
    defect_ids: List[str] = []
    for d in defects:
        d_keys = set(d.keys())
        missing_d = ORACLE_DEFECT_KEYS - d_keys
        if missing_d:
            errors.append(f"ORACLE_DEFECT_MISSING_KEYS: {sorted(missing_d)}")
        severity = d.get("severity", "")
        if severity not in {e.value for e in DefectSeverity}:
            errors.append(f"ORACLE_DEFECT_SEVERITY_INVALID: {severity!r}")
        did = d.get("defect_id", "")
        if did:
            defect_ids.append(did)

        # Validate that supporting refs exist in public case
        if case is not None:
            case_refs = {m.get("ref") for m in case.get("materials", [])}
            case_refs |= set(case.get("available_evidence_refs", []))
            for ref in d.get("supporting_public_refs", []):
                if ref not in case_refs:
                    errors.append(f"ORACLE_REF_NOT_IN_CASE: {ref!r}")

    # No duplicate defect IDs within case
    if len(set(defect_ids)) != len(defect_ids):
        errors.append("ORACLE_DUPLICATE_DEFECT_IDS")

    # Oracle hash
    sha = oracle.get("oracle_sha256", "")
    if not validate_sha256(sha):
        errors.append(f"ORACLE_SHA256_INVALID: {sha!r}")
    else:
        body = {k: v for k, v in oracle.items() if k != "oracle_sha256"}
        expected = compute_canonical_sha256(body)
        if expected != sha:
            errors.append("ORACLE_SHA256_MISMATCH")

    return errors


# ---------------------------------------------------------------------------
# Packet Contract
# ---------------------------------------------------------------------------

PACKET_EXACT_KEYS: Set[str] = {
    "schema", "benchmark_run_id", "arm", "arm_protocol_version",
    "case_alias", "case_version", "common_materials",
    "common_materials_sha256", "arm_overlay", "response_contract",
    "packet_sha256",
}

PACKET_FORBIDDEN_KEYS: Set[str] = {
    "case_id", "oracle", "oracle_class", "oracle_decision", "known_defects",
    "expected_answer", "required_detection", "defect_ids", "oracle_sha256",
}


def validate_packet(packet: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    keys = set(packet.keys())

    missing = PACKET_EXACT_KEYS - keys
    extra = keys - PACKET_EXACT_KEYS
    if missing:
        errors.append(f"PACKET_MISSING_KEYS: {sorted(missing)}")
    if extra:
        errors.append(f"PACKET_EXTRA_KEYS: {sorted(extra)}")

    leaked = PACKET_FORBIDDEN_KEYS & keys
    if leaked:
        errors.append(f"PACKET_FORBIDDEN_KEYS: {sorted(leaked)}")

    arm = packet.get("arm", "")
    if arm not in {e.value for e in BenchmarkArm}:
        errors.append(f"PACKET_ARM_INVALID: {arm!r}")

    sha = packet.get("packet_sha256", "")
    if not validate_sha256(sha):
        errors.append(f"PACKET_SHA256_INVALID: {sha!r}")
    else:
        body = {k: v for k, v in packet.items() if k != "packet_sha256"}
        expected = compute_canonical_sha256(body)
        if expected != sha:
            errors.append("PACKET_SHA256_MISMATCH")

    return errors


# ---------------------------------------------------------------------------
# Observation Contract
# ---------------------------------------------------------------------------

OBSERVATION_EXACT_KEYS: Set[str] = {
    "schema", "observation_id", "benchmark_run_id", "arm", "case_alias",
    "evaluator", "decision", "detected_defect_ids", "cited_evidence_refs",
    "rationale_summary", "confidence", "execution",
    "skipped_checks", "observation_sha256",
}

OBSERVATION_EVALUATOR_KEYS: Set[str] = {
    "evaluator_id", "provider", "model_id", "prompt_version",
}

OBSERVATION_EXECUTION_KEYS: Set[str] = {
    "started_at", "completed_at", "duration_seconds",
    "input_tokens", "output_tokens", "cost_usd",
}

OBSERVATION_FORBIDDEN_KEYS: Set[str] = {
    "chain_of_thought", "full_cot", "reasoning_chain",
    "oracle", "expected_answer",
}

_ISO8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


def _is_timezone_aware_iso8601(ts: str) -> bool:
    return bool(_ISO8601_RE.match(ts))


def validate_observation(obs: Dict[str, Any], packet: Optional[Dict[str, Any]] = None) -> List[str]:
    errors: List[str] = []
    keys = set(obs.keys())

    missing = OBSERVATION_EXACT_KEYS - keys
    extra = keys - OBSERVATION_EXACT_KEYS
    if missing:
        errors.append(f"OBS_MISSING_KEYS: {sorted(missing)}")
    if extra:
        errors.append(f"OBS_EXTRA_KEYS: {sorted(extra)}")

    leaked = OBSERVATION_FORBIDDEN_KEYS & keys
    if leaked:
        errors.append(f"OBS_FORBIDDEN_KEYS: {sorted(leaked)}")

    # arm
    arm = obs.get("arm", "")
    if arm not in {e.value for e in BenchmarkArm}:
        errors.append(f"OBS_ARM_INVALID: {arm!r}")

    # decision
    decision = obs.get("decision", "")
    if decision not in {e.value for e in BenchmarkDecision}:
        errors.append(f"OBS_DECISION_INVALID: {decision!r}")

    # confidence: must be int 0–100, not bool
    conf = obs.get("confidence")
    if conf is not None:
        if isinstance(conf, bool):
            errors.append("OBS_CONFIDENCE_IS_BOOL")
        elif not isinstance(conf, int) or conf < 0 or conf > 100:
            errors.append(f"OBS_CONFIDENCE_INVALID: {conf!r}")

    # rationale summary length
    rationale = obs.get("rationale_summary", "")
    if isinstance(rationale, str) and len(rationale) > 2000:
        errors.append("OBS_RATIONALE_TOO_LONG")

    # evaluator
    evaluator = obs.get("evaluator", {})
    if isinstance(evaluator, dict):
        ev_keys = set(evaluator.keys())
        missing_ev = OBSERVATION_EVALUATOR_KEYS - ev_keys
        if missing_ev:
            errors.append(f"OBS_EVALUATOR_MISSING_KEYS: {sorted(missing_ev)}")
    else:
        errors.append("OBS_EVALUATOR_NOT_DICT")

    # execution
    execution = obs.get("execution", {})
    if isinstance(execution, dict):
        ex_keys = set(execution.keys())
        missing_ex = OBSERVATION_EXECUTION_KEYS - ex_keys
        if missing_ex:
            errors.append(f"OBS_EXECUTION_MISSING_KEYS: {sorted(missing_ex)}")

        dur = execution.get("duration_seconds")
        if dur is not None and (isinstance(dur, bool) or (not isinstance(dur, (int, float))) or dur < 0):
            errors.append(f"OBS_DURATION_NEGATIVE: {dur!r}")

        for tok_field in ("input_tokens", "output_tokens"):
            tok = execution.get(tok_field)
            if tok is not None and (not isinstance(tok, int) or isinstance(tok, bool) or tok < 0):
                errors.append(f"OBS_TOKENS_INVALID: {tok_field}={tok!r}")

        cost = execution.get("cost_usd")
        if cost is not None and (isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0):
            errors.append(f"OBS_COST_NEGATIVE: {cost!r}")

        for ts_field in ("started_at", "completed_at"):
            ts = execution.get(ts_field, "")
            if ts and not _is_timezone_aware_iso8601(ts):
                errors.append(f"OBS_TIMESTAMP_NOT_AWARE: {ts_field}={ts!r}")
    else:
        errors.append("OBS_EXECUTION_NOT_DICT")

    # cited evidence refs must exist in packet
    cited_refs = obs.get("cited_evidence_refs", [])
    if packet is not None and isinstance(cited_refs, list):
        packet_refs = set()
        for m in packet.get("common_materials", {}).get("materials", []):
            packet_refs.add(m.get("ref", ""))
        for ref in packet.get("common_materials", {}).get("available_evidence_refs", []):
            packet_refs.add(ref)
        for ref in cited_refs:
            if ref and ref not in packet_refs:
                errors.append(f"OBS_CITED_REF_NOT_IN_PACKET: {ref!r}")

    # observation hash
    sha = obs.get("observation_sha256", "")
    if not validate_sha256(sha):
        errors.append(f"OBS_SHA256_INVALID: {sha!r}")
    else:
        body = {k: v for k, v in obs.items() if k != "observation_sha256"}
        expected = compute_canonical_sha256(body)
        if expected != sha:
            errors.append("OBS_SHA256_MISMATCH")

    return errors


# ---------------------------------------------------------------------------
# Report Contract
# ---------------------------------------------------------------------------

REPORT_EXACT_KEYS: Set[str] = {
    "schema", "benchmark_run", "corpus", "coverage", "arms",
    "comparisons", "limitations", "claim_ceiling", "report_sha256",
}

CLAIM_CEILING_TEXT = (
    "This benchmark report summarizes observations collected under versioned "
    "synthetic review protocols. It does not establish statistical significance, "
    "general research-quality improvement, production readiness, or that an "
    "epistemic ledger is necessary."
)

REQUIRED_LIMITATIONS: Tuple[str, ...] = (
    "synthetic corpus",
    "no live model calls performed by harness",
    "model/provider results depend on imported observations",
    "local repository access can defeat oracle isolation if packet boundaries are ignored",
    "small corpus",
    "no external validity claim",
    "no regulated-domain claim",
)

FORBIDDEN_REPORT_WORDS: Tuple[str, ...] = (
    "winner",
    "proven better",
    "statistically significant",
    "production ready",
    "arm c wins",
    "ledger proven",
    "research improved",
)

validate_case = validate_public_case
validate_oracle = validate_oracle_record
