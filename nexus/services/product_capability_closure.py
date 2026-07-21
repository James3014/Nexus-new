"""Fail-closed verification for the 34 PRODUCT capability closure matrix.

This module owns closure interpretation only.  It does not select capabilities,
add routes, or execute providers.  A runtime or harness must supply an execution
record whose hashes and verifier artifacts can be independently recomputed here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from nexus.services.capability_registry import (
    PLANNER_EXECUTION_CONTRACTS,
    REAL_EXECUTION_CLASSES,
)


LIVE_EXECUTED_PASS = "LIVE_EXECUTED_PASS"
POLICY_SKIP_VERIFIED = "POLICY_SKIP_VERIFIED"
BLOCKED_DEPENDENCY = "BLOCKED_DEPENDENCY"
EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
VERIFIER_FAILED = "VERIFIER_FAILED"
EXECUTION_FAILED = "EXECUTION_FAILED"
NOT_TESTED = "NOT_TESTED"

EVIDENCE_MODE_SIMULATION = "simulation"
EVIDENCE_MODE_HARNESS = "harness"
EVIDENCE_MODE_CANARY = "canary"
EVIDENCE_MODE_LIVE_PROVIDER = "live_provider"
EVIDENCE_MODES = frozenset({
    EVIDENCE_MODE_SIMULATION,
    EVIDENCE_MODE_HARNESS,
    EVIDENCE_MODE_CANARY,
    EVIDENCE_MODE_LIVE_PROVIDER,
})

PRODUCT_CAPABILITIES = tuple(
    sorted(
        name
        for name, contract in PLANNER_EXECUTION_CONTRACTS.items()
        if contract.get("execution_class") in REAL_EXECUTION_CLASSES
    )
)

_ALLOWED_RESOLUTIONS = {
    "online": frozenset(
        {
            "ONLINE_NATIVE",
            "ONLINE_STAGE_OWNED",
            "ONLINE_TO_LOCAL_GOVERNED_BRIDGE",
        }
    ),
    "local": frozenset(
        {
            "LOCAL_NATIVE",
            "LOCAL_STAGE_OWNED",
            "LOCAL_TO_ONLINE_GOVERNED_BRIDGE",
        }
    ),
}
_FAIL_STATUSES = frozenset(
    {
        "FAILED",
        "FAIL",
        "BLOCKED",
        "BLOCKED_EXECUTOR_UNAVAILABLE",
        "ERROR",
        "UNVERIFIED",
    }
)
_SYNTHETIC_MARKERS = (
    "fixture",
    "fakecloud",
    "fake_cloud",
    "shadow",
    "injected_transport",
    "test:",
    "synthetic",
)
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ASSIST_LINEAGE_FIELDS = (
    "packet_hash",
    "fragment_hash",
    "final_prompt_hash",
    "online_candidate_hash",
    "applied_artifact_hash",
    "verifier_artifact_hash",
    "final_receipt_hash",
)

from nexus.services.capability_registry import (
    CONSUMER_MODES,
    PLANNER_EXECUTION_CONTRACTS,
    REAL_EXECUTION_CLASSES,
    project_consumer_execution_mode,
)

_ALLOWED_RESOLUTIONS = {
    "online": frozenset(
        CONSUMER_MODES
        | {
            "ONLINE_NATIVE",
            "ONLINE_STAGE_OWNED",
            "ONLINE_TO_LOCAL_GOVERNED_BRIDGE",
        }
    ),
    "local": frozenset(
        CONSUMER_MODES
        | {
            "LOCAL_NATIVE",
            "LOCAL_STAGE_OWNED",
            "LOCAL_TO_ONLINE_GOVERNED_BRIDGE",
        }
    ),
}
_RESOLUTION_EQUIVALENCE = {
    "ONLINE_NATIVE": "CONSUME_SHARED_EVIDENCE",
    "ONLINE_TO_LOCAL_GOVERNED_BRIDGE": "CONSUME_SHARED_EVIDENCE",
    "ONLINE_STAGE_OWNED": "CONTROLLED_BY_POSTFLIGHT",
    "LOCAL_NATIVE": "EXECUTE_HERE",
    "LOCAL_STAGE_OWNED": "EXECUTE_HERE",
    "LOCAL_TO_ONLINE_GOVERNED_BRIDGE": "CONSUME_SHARED_EVIDENCE",
}


def expected_resolution_type(origin: str, capability: str) -> str:
    """Return the allowed resolution assigned to a 34×2 matrix cell derived from SSOT."""
    normalized_origin = str(origin or "").lower()
    normalized_capability = str(capability or "")
    if normalized_origin not in {"online", "local"}:
        raise ValueError(f"unsupported origin: {origin!r}")
    if normalized_capability not in PLANNER_EXECUTION_CONTRACTS:
        raise ValueError(f"unsupported capability: {capability!r}")
    return project_consumer_execution_mode(normalized_capability, normalized_origin)


def _is_equivalent_resolution(provided: str, expected_ssot_mode: str) -> bool:
    if provided == expected_ssot_mode:
        return True
    return _RESOLUTION_EQUIVALENCE.get(provided) == expected_ssot_mode



def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_hash(value: Any) -> bool:
    return bool(_HASH_RE.fullmatch(str(value or "").lower()))


def _hash_matches(payload: Any, claimed_hash: Any) -> bool:
    return payload is not None and _valid_hash(claimed_hash) and _canonical_hash(payload) == str(
        claimed_hash
    ).lower()


def _is_synthetic(record: Mapping[str, Any]) -> bool:
    fields = (
        record.get("provider"),
        record.get("transport"),
        record.get("physical_callable"),
        record.get("execution_surface"),
    )
    text = " ".join(str(value or "").lower() for value in fields)
    return any(marker in text for marker in _SYNTHETIC_MARKERS)


def _blocker_evidence_present(refs: Any) -> bool:
    if not isinstance(refs, (list, tuple)):
        return False
    for ref in refs:
        if isinstance(ref, str) and ref.lower().startswith("blocker:"):
            return True
        if isinstance(ref, Mapping):
            status = str(ref.get("status") or ref.get("type") or "").lower()
            if status == "blocker" or str(ref.get("ref") or "").lower().startswith(
                "blocker:"
            ):
                return True
    return False


def _structured_evidence_ok(refs: Any) -> bool:
    if not isinstance(refs, (list, tuple)) or not refs:
        return False
    for ref in refs:
        if not isinstance(ref, Mapping):
            return False
        if not str(ref.get("path") or "").strip():
            return False
        if not _hash_matches(ref.get("payload"), ref.get("sha256")):
            return False
    return True


def _effect_ok(effect: Any) -> bool:
    item = _mapping(effect)
    return bool(
        str(item.get("effect_type") or "").strip()
        and _hash_matches(item.get("artifact_payload"), item.get("artifact_hash"))
    )


def _verifier_evidence_complete(verifier: Mapping[str, Any]) -> bool:
    return bool(
        verifier.get("invoked") is True
        and _hash_matches(verifier.get("evidence_payload"), verifier.get("evidence_hash"))
        and _hash_matches(verifier.get("artifact_payload"), verifier.get("artifact_hash"))
    )


def _local_execution_reasons(
    capability: str, local_execution: Mapping[str, Any]
) -> tuple[list[str], list[str]]:
    execution_failures: list[str] = []
    evidence_failures: list[str] = []
    if local_execution.get("model_called") is not True:
        execution_failures.append("local_model_not_called")
    if local_execution.get("output_delivered") is not True:
        execution_failures.append("local_output_not_delivered")
    if local_execution.get("candidate_isolated") is not True:
        evidence_failures.append("candidate_not_isolated")
    for field in ("candidate_hash", "selected_hash", "applied_hash"):
        if not _valid_hash(local_execution.get(field)):
            evidence_failures.append(f"missing_or_invalid_{field}")
    selected_hash = str(local_execution.get("selected_hash") or "")
    applied_hash = str(local_execution.get("applied_hash") or "")
    if _valid_hash(selected_hash) and _valid_hash(applied_hash) and selected_hash != applied_hash:
        evidence_failures.append("selected_applied_hash_mismatch")
    if not str(local_execution.get("provider_family") or "").strip():
        evidence_failures.append("local_provider_family_missing")
    if not str(local_execution.get("model_name") or "").strip():
        evidence_failures.append("local_model_name_missing")
    if capability == "repair_loop" and local_execution.get("loop_entered") is not True:
        execution_failures.append("repair_loop_not_entered")
    return execution_failures, evidence_failures


_MANDATORY_PAYLOAD_HASH_PAIRS = (
    ("packet_payload", "packet_hash"),
    ("fragment_payload", "fragment_hash"),
    ("final_prompt_payload", "final_prompt_hash"),
    ("online_candidate_payload", "online_candidate_hash"),
    ("applied_artifact_payload", "applied_artifact_hash"),
    ("verifier_artifact_payload", "verifier_artifact_hash"),
    ("final_receipt_payload", "final_receipt_hash"),
)


def _assist_lineage_complete(lineage: Mapping[str, Any], record: Mapping[str, Any] | None = None) -> bool:
    if not isinstance(lineage, Mapping):
        return False

    # 1. Require all 7 hash fields to be valid 64-hex
    if not all(_valid_hash(lineage.get(hash_key)) for _, hash_key in _MANDATORY_PAYLOAD_HASH_PAIRS):
        return False

    # 2. Require all 7 payload dictionaries to be present
    for payload_key, hash_key in _MANDATORY_PAYLOAD_HASH_PAIRS:
        payload = lineage.get(payload_key)
        if not isinstance(payload, Mapping) or not payload:
            return False
        claimed_hash = str(lineage.get(hash_key) or "").lower()
        if _canonical_hash(payload) != claimed_hash:
            return False

    # 3. Identity binding: task_id, workspace_revision, planner_decision_id
    if record is not None:
        for field in ("task_id", "workspace_revision", "planner_decision_id"):
            rec_val = str(record.get(field) or "").strip()
            lin_val = str(lineage.get(field) or "").strip()
            if rec_val and lin_val and rec_val != lin_val:
                return False

    # 4. Adjacent edge binding check
    packet_hash = str(lineage.get("packet_hash") or "").lower()
    fragment_payload = _mapping(lineage.get("fragment_payload"))
    if not (
        packet_hash in str(fragment_payload.get("packet_hash") or "").lower()
        or packet_hash in str(fragment_payload.get("parent_hash") or "").lower()
        or packet_hash in json.dumps(fragment_payload, default=str)
    ):
        return False

    fragment_hash = str(lineage.get("fragment_hash") or "").lower()
    final_prompt_payload = _mapping(lineage.get("final_prompt_payload"))
    if not (
        fragment_hash in str(final_prompt_payload.get("fragment_hash") or "").lower()
        or fragment_hash in json.dumps(final_prompt_payload, default=str)
    ):
        return False

    final_prompt_hash = str(lineage.get("final_prompt_hash") or "").lower()
    online_candidate_payload = _mapping(lineage.get("online_candidate_payload"))
    if not (
        final_prompt_hash in str(online_candidate_payload.get("final_prompt_hash") or "").lower()
        or final_prompt_hash in str(online_candidate_payload.get("prompt_hash") or "").lower()
        or final_prompt_hash in json.dumps(online_candidate_payload, default=str)
    ):
        return False

    online_candidate_hash = str(lineage.get("online_candidate_hash") or "").lower()
    applied_artifact_payload = _mapping(lineage.get("applied_artifact_payload"))
    if not (
        online_candidate_hash in str(applied_artifact_payload.get("online_candidate_hash") or "").lower()
        or online_candidate_hash in str(applied_artifact_payload.get("candidate_hash") or "").lower()
        or online_candidate_hash in json.dumps(applied_artifact_payload, default=str)
    ):
        return False

    applied_artifact_hash = str(lineage.get("applied_artifact_hash") or "").lower()
    verifier_artifact_payload = _mapping(lineage.get("verifier_artifact_payload"))
    if not (
        applied_artifact_hash in str(verifier_artifact_payload.get("applied_artifact_hash") or "").lower()
        or applied_artifact_hash in str(verifier_artifact_payload.get("applied_hash") or "").lower()
        or applied_artifact_hash in json.dumps(verifier_artifact_payload, default=str)
    ):
        return False

    verifier_artifact_hash = str(lineage.get("verifier_artifact_hash") or "").lower()
    final_receipt_payload = _mapping(lineage.get("final_receipt_payload"))
    if not (
        verifier_artifact_hash in str(final_receipt_payload.get("verifier_artifact_hash") or "").lower()
        or verifier_artifact_hash in str(final_receipt_payload.get("verifier_hash") or "").lower()
        or verifier_artifact_hash in json.dumps(final_receipt_payload, default=str)
    ):
        return False

    return True


def _physical_evidence_verify(
    evidence_ref: Mapping[str, Any],
    run_root: str | Path | None = None,
) -> list[str]:
    """Verify a single evidence reference has a physical file with matching hash.

    Returns a list of failure reasons (empty = pass).
    """
    failures: list[str] = []
    path_str = str(evidence_ref.get("path") or "").strip()
    claimed_sha = str(evidence_ref.get("sha256") or "").strip()
    payload = evidence_ref.get("payload")

    if not path_str:
        failures.append("evidence_path_missing")
        return failures

    evidence_path = Path(path_str)
    if not evidence_path.exists():
        failures.append("evidence_file_not_found")
        return failures

    if evidence_path.is_symlink():
        real_target = evidence_path.resolve()
        if run_root is not None:
            run_root_resolved = Path(run_root).resolve()
            try:
                real_target.relative_to(run_root_resolved)
            except ValueError:
                failures.append("symlink_escape_detected")
                return failures
        failures.append("symlink_evidence_not_allowed")
        return failures

    if run_root is not None:
        run_root_resolved = Path(run_root).resolve()
        try:
            evidence_path.resolve().relative_to(run_root_resolved)
        except ValueError:
            failures.append("path_traversal_detected")
            return failures

    try:
        actual_bytes = evidence_path.read_bytes()
    except OSError:
        failures.append("evidence_file_unreadable")
        return failures

    actual_hash = hashlib.sha256(actual_bytes).hexdigest()
    if claimed_sha and actual_hash != claimed_sha.lower():
        failures.append("evidence_hash_mismatch")
        return failures

    if payload is not None:
        recomputed = _canonical_hash(payload)
        if recomputed != actual_hash:
            failures.append("evidence_payload_hash_mismatch")

    try:
        decoded = actual_bytes.decode("utf-8")
        json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError):
        failures.append("evidence_file_not_valid_json")
        return failures

    if evidence_ref.get("raw_output") is not None:
        raw_output = evidence_ref["raw_output"]
        if isinstance(raw_output, str):
            raw_bytes = raw_output.encode("utf-8")
        elif isinstance(raw_output, bytes):
            raw_bytes = raw_output
        else:
            failures.append("provider_raw_output_invalid_type")
            return failures
        raw_claimed = evidence_ref.get("raw_output_sha256") or ""
        if raw_claimed and hashlib.sha256(raw_bytes).hexdigest() != raw_claimed.lower():
            failures.append("provider_raw_output_hash_mismatch")
            return failures
    elif claimed_sha:
        failures.append("provider_raw_output_missing")
        return failures

    if evidence_ref.get("adapter_claimed_success") is True and not evidence_ref.get("raw_output"):
        failures.append("adapter_synthesized_without_raw_provider_output")
        return failures

    return failures


def _evidence_mode_classify(record: Mapping[str, Any]) -> str:
    """Determine evidence mode from record fields. Unknown mode fails closed."""
    mode = str(record.get("evidence_mode") or "").strip().lower()
    if mode in EVIDENCE_MODES:
        return mode
    if mode:
        return mode

    provider = str(record.get("provider") or "").lower()
    transport = str(record.get("transport") or "").lower()
    physical = str(record.get("physical_callable") or "").lower()

    if any(m in provider for m in ("fixture", "fake", "synthetic", "shadow", "injected")):
        return EVIDENCE_MODE_SIMULATION
    if any(m in transport for m in ("fixture", "fake", "synthetic", "shadow", "injected")):
        return EVIDENCE_MODE_SIMULATION
    if any(m in physical for m in ("fixture", "test:", "synthetic")):
        return EVIDENCE_MODE_SIMULATION

    if record.get("planner_selected") is True and record.get("invoked") is True:
        online = record.get("online")
        if isinstance(online, Mapping) and online.get("invoked") is True:
            return EVIDENCE_MODE_CANARY

    return EVIDENCE_MODE_SIMULATION


def _verdict(
    record: Mapping[str, Any],
    *,
    status: str,
    reasons: list[str],
) -> dict[str, Any]:
    refs = record.get("evidence_refs")
    accepted_refs = [dict(ref) for ref in refs or [] if isinstance(ref, Mapping)]
    evidence_path = str(accepted_refs[0].get("path") or "") if accepted_refs else ""
    live_pass = status == LIVE_EXECUTED_PASS and not reasons
    return {
        "schema": "nexus.product_capability_closure_verdict.v1",
        "capability": str(record.get("capability") or ""),
        "origin": str(record.get("origin") or ""),
        "resolution_type": str(record.get("resolution_type") or ""),
        "evidence_mode": str(record.get("evidence_mode") or ""),
        "status": status,
        "live_pass": live_pass,
        "gate_verdict": "PASS" if live_pass else "BLOCK_OR_RETURN",
        "acceptance_evidence_refs": accepted_refs,
        "missing_evidence_reasons": list(dict.fromkeys(reasons)),
        "receipt_path": str(record.get("receipt_path") or ""),
        "evidence_path": evidence_path,
        "public_claim_allowed": False,
    }


def verify_product_capability_resolution(record: Mapping[str, Any]) -> dict[str, Any]:
    """Independently classify one origin/capability execution record.

    Producer-provided summary booleans such as ``live_closure_pass`` and
    ``terminal_status=PASS`` are intentionally ignored.
    """

    capability = str(record.get("capability") or "")
    origin = str(record.get("origin") or "").lower()
    resolution = str(record.get("resolution_type") or "")
    status = str(record.get("status") or "").upper()

    if capability not in PRODUCT_CAPABILITIES:
        return _verdict(record, status=NOT_TESTED, reasons=["capability_not_in_product_denominator"])
    if origin not in _ALLOWED_RESOLUTIONS:
        return _verdict(record, status=NOT_TESTED, reasons=["invalid_origin"])
    if resolution not in _ALLOWED_RESOLUTIONS[origin]:
        return _verdict(record, status=NOT_TESTED, reasons=["invalid_resolution_type"])
    expected_resolution = expected_resolution_type(origin, capability)
    if not _is_equivalent_resolution(resolution, expected_resolution):
        return _verdict(record, status=NOT_TESTED, reasons=["unexpected_resolution_type"])
    if record.get("skipped") is True or status.startswith("SKIPPED"):
        return _verdict(record, status=POLICY_SKIP_VERIFIED, reasons=["policy_skip_not_live_pass"])
    if record.get("planner_selected") is not True:
        return _verdict(record, status=NOT_TESTED, reasons=["planner_did_not_select_capability"])
    if record.get("trigger_condition_met") is not True:
        return _verdict(record, status=NOT_TESTED, reasons=["trigger_condition_not_met"])
    if status == "SELECTED_NOT_EXECUTED" or record.get("invoked") is not True:
        return _verdict(record, status=BLOCKED_DEPENDENCY, reasons=["selected_not_executed"])
    if status in _FAIL_STATUSES:
        return _verdict(record, status=EXECUTION_FAILED, reasons=[f"execution_status:{status.lower()}"])

    refs = record.get("evidence_refs")
    if _blocker_evidence_present(refs):
        return _verdict(record, status=BLOCKED_DEPENDENCY, reasons=["blocker_evidence_present"])
    if _is_synthetic(record):
        return _verdict(
            record,
            status=EVIDENCE_INCOMPLETE,
            reasons=["synthetic_or_fixture_execution"],
        )
    consistency_errors = list(record.get("harness_consistency_errors") or [])
    if consistency_errors:
        return _verdict(
            record,
            status=EVIDENCE_INCOMPLETE,
            reasons=[f"harness_consistency:{error}" for error in consistency_errors],
        )
    if record.get("route_surface_changed") is not False:
        return _verdict(
            record,
            status=EVIDENCE_INCOMPLETE,
            reasons=["route_surface_changed_or_unproven"],
        )
    if record.get("public_claim_allowed") is not False:
        return _verdict(
            record,
            status=EVIDENCE_INCOMPLETE,
            reasons=["claim_boundary_not_fail_closed"],
        )

    task_id = str(record.get("task_id") or "").strip()
    if not task_id:
        return _verdict(record, status=EVIDENCE_INCOMPLETE, reasons=["task_id_missing"])
    if not str(record.get("planner_decision_id") or "").strip():
        return _verdict(record, status=EVIDENCE_INCOMPLETE, reasons=["planner_decision_id_missing"])

    evidence_mode = _evidence_mode_classify(record)
    if evidence_mode not in EVIDENCE_MODES:
        return _verdict(
            record,
            status=EVIDENCE_INCOMPLETE,
            reasons=["evidence_mode_unknown"],
        )

    if record.get("live_pass") is True and evidence_mode != EVIDENCE_MODE_LIVE_PROVIDER:
        return _verdict(
            record,
            status=EVIDENCE_INCOMPLETE,
            reasons=[f"producer_claimed_live_pass_in_{evidence_mode}_mode"],
        )

    if record.get("gate_passed") is True and evidence_mode != EVIDENCE_MODE_LIVE_PROVIDER:
        return _verdict(
            record,
            status=EVIDENCE_INCOMPLETE,
            reasons=[f"producer_claimed_gate_passed_in_{evidence_mode}_mode"],
        )

    if record.get("lineage_recomputed") is True:
        independent_check = _hash_matches(
            record.get("receipt_payload"), record.get("receipt_hash")
        )
        if not independent_check:
            return _verdict(
                record,
                status=EVIDENCE_INCOMPLETE,
                reasons=["lineage_recomputed_without_independent_verification"],
            )

    missing: list[str] = []
    if not str(record.get("physical_callable") or "").strip():
        missing.append("physical_callable_missing")
    if not _structured_evidence_ok(refs):
        missing.append("structured_evidence_not_verified")
    if record.get("structured_evidence_verified") is not True:
        missing.append("structured_evidence_verdict_missing")
    if not _effect_ok(record.get("observable_effect")):
        missing.append("observable_effect_not_verified")
    if not _hash_matches(record.get("receipt_payload"), record.get("receipt_hash")):
        missing.append("receipt_hash_not_verified")

    verifier = _mapping(record.get("verifier"))
    if verifier.get("invoked") is True and verifier.get("passed") is False:
        return _verdict(record, status=VERIFIER_FAILED, reasons=["verifier_failed"])
    if not _verifier_evidence_complete(verifier):
        missing.append("verifier_evidence_incomplete")
    if record.get("gate_passed") is not True:
        return _verdict(record, status=VERIFIER_FAILED, reasons=["gate_not_passed", *missing])

    if capability in {"local_model_executor", "repair_loop"}:
        execution_failures, local_missing = _local_execution_reasons(
            capability, _mapping(record.get("local_execution"))
        )
        if execution_failures:
            return _verdict(record, status=EXECUTION_FAILED, reasons=execution_failures)
        missing.extend(local_missing)

    if (
        resolution == "LOCAL_TO_ONLINE_GOVERNED_BRIDGE"
        or (origin == "local" and expected_resolution == "CONSUME_SHARED_EVIDENCE")
    ) and not _assist_lineage_complete(_mapping(record.get("assist_lineage")), record):
        missing.append("assist_lineage_incomplete")

    if evidence_mode == EVIDENCE_MODE_LIVE_PROVIDER:
        run_root = str(record.get("run_root") or "").strip() or None
        for ref in (refs or []):
            if isinstance(ref, Mapping):
                phys_failures = _physical_evidence_verify(ref, run_root=run_root)
                missing.extend(phys_failures)

    if missing:
        return _verdict(record, status=EVIDENCE_INCOMPLETE, reasons=missing)
    return _verdict(record, status=LIVE_EXECUTED_PASS, reasons=[])


def summarize_origin_matrix(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize exactly one record for each 34 × 2 expected matrix key."""

    rows = [dict(record) for record in records]
    keyed: dict[tuple[str, str], dict[str, Any]] = {}
    duplicates: list[str] = []
    for row in rows:
        key = (str(row.get("origin") or "").lower(), str(row.get("capability") or ""))
        if key in keyed:
            duplicates.append(f"{key[0]}:{key[1]}")
            continue
        keyed[key] = row

    expected = {
        (origin, capability)
        for origin in ("online", "local")
        for capability in PRODUCT_CAPABILITIES
    }
    missing_keys = sorted(f"{origin}:{capability}" for origin, capability in expected - set(keyed))
    verdicts = [verify_product_capability_resolution(keyed[key]) for key in sorted(expected & set(keyed))]
    counts = Counter(str(verdict.get("status") or NOT_TESTED) for verdict in verdicts)
    online_pass = sum(
        1
        for verdict in verdicts
        if verdict.get("origin") == "online" and verdict.get("live_pass") is True
    )
    local_pass = sum(
        1
        for verdict in verdicts
        if verdict.get("origin") == "local" and verdict.get("live_pass") is True
    )
    matrix_pass = online_pass + local_pass
    route_surface_changed = any(bool(row.get("route_surface_changed")) for row in rows)
    receipt_hash_verified_count = sum(
        1
        for key, row in keyed.items()
        if key in expected and _hash_matches(row.get("receipt_payload"), row.get("receipt_hash"))
    )
    policy_skip_pass_count = sum(
        1
        for verdict in verdicts
        if verdict.get("live_pass") is True
        and keyed[(str(verdict["origin"]), str(verdict["capability"]))].get("skipped") is True
    )
    synthetic_live_pass = sum(
        1
        for verdict in verdicts
        if verdict.get("live_pass") is True
        and _is_synthetic(keyed[(str(verdict["origin"]), str(verdict["capability"]))])
    )
    complete = bool(
        not missing_keys
        and not duplicates
        and len(rows) == 68
        and matrix_pass == 68
        and not route_surface_changed
    )
    return {
        "schema": "nexus.product_capability_origin_matrix_summary.v1",
        "product_capabilities": len(PRODUCT_CAPABILITIES),
        "online_origin_pass": online_pass,
        "local_origin_pass": local_pass,
        "matrix_pass": matrix_pass,
        "matrix_total": 68,
        "complete": complete,
        "status_counts": dict(sorted(counts.items())),
        "policy_skip_count": counts.get(POLICY_SKIP_VERIFIED, 0),
        "policy_skip_pass_count": policy_skip_pass_count,
        "synthetic_live_pass": synthetic_live_pass,
        "receipt_hash_verified_count": receipt_hash_verified_count,
        "missing_keys": missing_keys,
        "duplicate_keys": sorted(set(duplicates)),
        "route_surface_changed": route_surface_changed,
        "public_claim_allowed": False,
        "verdicts": verdicts,
    }


if len(PRODUCT_CAPABILITIES) != 34:  # pragma: no cover - import-time contract guard
    raise RuntimeError(
        "PRODUCT denominator drift: expected 34 REAL execution contracts, "
        f"got {len(PRODUCT_CAPABILITIES)}"
    )
