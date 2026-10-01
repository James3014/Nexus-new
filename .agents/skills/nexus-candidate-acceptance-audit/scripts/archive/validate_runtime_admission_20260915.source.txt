#!/usr/bin/env python3
"""Validate execution-time Workforce Admission against one READY compiled packet."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from pathlib import Path
from typing import Any

PACKET_SCHEMA = "nexus.compiled_model_task_packet.v3"
RESULT_SCHEMA = "nexus.runtime_workforce_admission.v1"
RECORD_SCHEMA = "nexus.runtime_workforce_admission_record.v1"
DEMAND_SCHEMA = "nexus.workforce_demand.v1"
REQUEST_SCHEMA = "nexus.workforce_admission_request.v1"
DECISION_SCHEMA = "nexus.workforce_admission_decision.v1"
ROUTE_AUTHORITY = "CapabilityPlanner"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
DECISIONS = {"ALLOW", "BLOCK", "ESCALATE"}


class DuplicateKeyError(ValueError):
    pass


def no_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime_admission", type=Path)
    parser.add_argument("compiled_packet", type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def safe_json_file(path: Path, label: str, max_bytes: int = 4 * 1024 * 1024) -> tuple[dict[str, Any], str]:
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise OSError(f"{label}: unsafe JSON file")
    if info.st_size > max_bytes:
        raise OSError(f"{label}: exceeds {max_bytes} bytes")
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicate_pairs)
    if not isinstance(value, dict):
        raise ValueError(f"{label}: object required")
    return value, hashlib.sha256(raw).hexdigest()


def _obj(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    return value if isinstance(value, dict) else {}


def _list(parent: dict[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    return value if isinstance(value, list) else []


def _binding_payload(record: dict[str, Any], policy_hash: str) -> dict[str, Any]:
    demand = _obj(record, "demand")
    request = _obj(record, "request")
    decision = _obj(record, "decision")
    return {
        "schema": "nexus.runtime_workforce_binding.v1",
        "policy_hash": policy_hash,
        "demand_id": demand.get("demand_id"),
        "execution_channel": demand.get("execution_channel"),
        "requested_worker_id": request.get("requested_worker_id"),
        "requested_provider": request.get("provider"),
        "requested_model": request.get("model"),
        "resolved_worker_id": decision.get("resolved_worker_id"),
        "resolved_provider": decision.get("resolved_provider"),
        "resolved_model": decision.get("resolved_model"),
        "requested_role": request.get("role"),
        "admitted_role": decision.get("admitted_role"),
        "requested_autonomy": request.get("autonomy"),
        "admitted_autonomy": decision.get("admitted_autonomy"),
        "requested_context": request.get("context"),
        "admitted_context": decision.get("admitted_context"),
        "decision": decision.get("decision", "BLOCK"),
        "required_controls": sorted(str(item) for item in (decision.get("required_controls") or ())),
        "missing_controls": sorted(str(item) for item in (decision.get("missing_controls") or ())),
        "route_authority": demand.get("route_authority"),
        "explicit_experiment_authorization": bool(request.get("explicit_experiment_authorization", False)),
    }


def _validate_result_structure(receipt: dict[str, Any], prefix: str, errors: list[str]) -> tuple[str, list[dict[str, Any]]]:
    if receipt.get("schema") != RESULT_SCHEMA:
        errors.append(f"{prefix}.schema: expected {RESULT_SCHEMA}")
    policy = _obj(receipt, "policy_identity")
    policy_hash = str(policy.get("policy_hash") or "")
    if not HEX64.fullmatch(policy_hash):
        errors.append(f"{prefix}.policy_identity.policy_hash: 64 lowercase hex required")
    if policy.get("route_authority") != ROUTE_AUTHORITY:
        errors.append(f"{prefix}.policy_identity.route_authority: CapabilityPlanner required")
    if not isinstance(policy.get("status"), str) or not str(policy.get("status")).strip() or str(policy.get("status")).upper() == "BLOCKED":
        errors.append(f"{prefix}.policy_identity.status: active/non-blocked policy required")

    raw_records = receipt.get("records")
    if not isinstance(raw_records, list):
        errors.append(f"{prefix}.records: array required")
        raw_records = []
    records: list[dict[str, Any]] = []
    record_hashes: list[str] = []
    decisions: list[str] = []
    for index, raw in enumerate(raw_records):
        path = f"{prefix}.records[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{path}: object required")
            continue
        records.append(raw)
        if raw.get("schema") != RECORD_SCHEMA:
            errors.append(f"{path}.schema: expected {RECORD_SCHEMA}")
        demand = _obj(raw, "demand")
        request = _obj(raw, "request")
        decision = _obj(raw, "decision")
        if demand.get("schema") != DEMAND_SCHEMA:
            errors.append(f"{path}.demand.schema: expected {DEMAND_SCHEMA}")
        if request.get("schema") != REQUEST_SCHEMA:
            errors.append(f"{path}.request.schema: expected {REQUEST_SCHEMA}")
        if decision.get("schema") != DECISION_SCHEMA:
            errors.append(f"{path}.decision.schema: expected {DECISION_SCHEMA}")
        if demand.get("route_authority") != ROUTE_AUTHORITY:
            errors.append(f"{path}.demand.route_authority: CapabilityPlanner required")
        if decision.get("route_authority") != ROUTE_AUTHORITY:
            errors.append(f"{path}.decision.route_authority: CapabilityPlanner required")
        if decision.get("policy_hash") != policy_hash:
            errors.append(f"{path}.decision.policy_hash: must match policy_identity")
        freshness = decision.get("freshness_evidence")
        if isinstance(freshness, dict) and freshness.get("is_future") is True:
            errors.append(f"{path}.decision.freshness_evidence: future policy verification is invalid")
        decision_value = decision.get("decision")
        if decision_value not in DECISIONS:
            errors.append(f"{path}.decision.decision: ALLOW, BLOCK, or ESCALATE required")
        else:
            decisions.append(str(decision_value))
        binding_hash = raw.get("binding_hash")
        if not isinstance(binding_hash, str) or not HEX64.fullmatch(binding_hash):
            errors.append(f"{path}.binding_hash: 64 lowercase hex required")
        else:
            record_hashes.append(binding_hash)
            expected = sha256_json(_binding_payload(raw, policy_hash))
            if binding_hash != expected:
                errors.append(f"{path}.binding_hash: does not match canonical binding payload")

    aggregate = receipt.get("aggregate_binding_hash")
    expected_aggregate = sha256_json({"policy_hash": policy_hash, "record_hashes": record_hashes})
    if not isinstance(aggregate, str) or not HEX64.fullmatch(aggregate):
        errors.append(f"{prefix}.aggregate_binding_hash: 64 lowercase hex required")
    elif aggregate != expected_aggregate:
        errors.append(f"{prefix}.aggregate_binding_hash: does not match record bindings")

    derived_overall = "BLOCK" if not decisions or "BLOCK" in decisions else ("ESCALATE" if "ESCALATE" in decisions else "ALLOW")
    if receipt.get("overall_decision") != derived_overall:
        errors.append(f"{prefix}.overall_decision: does not match record decisions")
    return policy_hash, records


def _record_semantics(record: dict[str, Any]) -> dict[str, Any]:
    demand = _obj(record, "demand")
    request = _obj(record, "request")
    decision = _obj(record, "decision")
    return {
        "worker_id": decision.get("resolved_worker_id"),
        "provider": decision.get("resolved_provider"),
        "model_id": decision.get("resolved_model"),
        "workforce_role": decision.get("admitted_role"),
        "autonomy": decision.get("admitted_autonomy"),
        "context_class": decision.get("admitted_context"),
        "execution_channel": demand.get("execution_channel"),
        "mutation_intent": demand.get("mutation_intent"),
        "request_mutation": request.get("mutation_requested"),
        "decision": decision.get("decision"),
    }


def validate_compiled_packet_workforce(packet: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if packet.get("schema") != PACKET_SCHEMA:
        errors.append(f"$.schema: expected {PACKET_SCHEMA}")
    if packet.get("status") != "READY":
        errors.append("$.status: READY compiled packet required")
    compiler = _obj(packet, "compiler")
    attempt = _obj(packet, "attempt")
    transport = _obj(packet, "transport")
    scope = _obj(packet, "scope")
    workforce = _obj(packet, "workforce_admission")
    if not workforce:
        errors.append("$.workforce_admission: object required")
        return {"valid": False, "errors": errors, "policy_hash": None, "selected": None}
    receipt = workforce.get("receipt")
    if not isinstance(receipt, dict):
        errors.append("$.workforce_admission.receipt: object required")
        return {"valid": False, "errors": errors, "policy_hash": None, "selected": None}

    policy_hash, records = _validate_result_structure(receipt, "$.workforce_admission.receipt", errors)
    if receipt.get("overall_decision") != "ALLOW":
        errors.append("$.workforce_admission.receipt.overall_decision: ALLOW required")
    if compiler.get("policy_snapshot") != policy_hash:
        errors.append("$.compiler.policy_snapshot: must match workforce policy hash")
    if transport.get("execution_ready") is not True:
        errors.append("$.transport.execution_ready: true required for READY packet")

    selected_hash = workforce.get("selected_record_binding_hash")
    if not isinstance(selected_hash, str) or not HEX64.fullmatch(selected_hash):
        errors.append("$.workforce_admission.selected_record_binding_hash: 64 lowercase hex required")
        selected_record = None
    else:
        matches = [record for record in records if record.get("binding_hash") == selected_hash]
        if len(matches) != 1:
            errors.append("$.workforce_admission.selected_record_binding_hash: must select exactly one record")
            selected_record = None
        else:
            selected_record = matches[0]

    selected: dict[str, Any] | None = None
    if selected_record is not None:
        demand = _obj(selected_record, "demand")
        request = _obj(selected_record, "request")
        decision = _obj(selected_record, "decision")
        if decision.get("decision") != "ALLOW":
            errors.append("$.workforce_admission: selected decision must be ALLOW")
        if request.get("route_authorized") is not True:
            errors.append("$.workforce_admission: selected request route_authorized=true required")
        missing_controls = decision.get("missing_controls")
        if not isinstance(missing_controls, list) or missing_controls:
            errors.append("$.workforce_admission: selected ALLOW requires missing_controls=[]")
        required = decision.get("required_controls") if isinstance(decision.get("required_controls"), list) else []
        provided = request.get("provided_controls") if isinstance(request.get("provided_controls"), list) else []
        if not set(map(str, required)).issubset(set(map(str, provided))):
            errors.append("$.workforce_admission: required controls not covered by provided controls")

        expected = {
            "worker_id": attempt.get("worker_id"),
            "provider": attempt.get("provider"),
            "model_id": attempt.get("model_id"),
            "workforce_role": attempt.get("workforce_role"),
            "autonomy": attempt.get("autonomy"),
            "context_class": attempt.get("context_class"),
            "execution_channel": attempt.get("execution_channel"),
        }
        observed = _record_semantics(selected_record)
        for key, value in expected.items():
            if observed.get(key) != value:
                errors.append(f"$.workforce_admission: selected {key} mismatch")
        mutation_required = bool(scope.get("edit_paths") or scope.get("create_paths") or scope.get("delete_paths"))
        if observed.get("mutation_intent") is not mutation_required or observed.get("request_mutation") is not mutation_required:
            errors.append("$.workforce_admission: mutation intent/request mismatch")
        selected = {**expected, "mutation_intent": mutation_required, "binding_hash": selected_record.get("binding_hash")}

    return {"valid": not errors, "errors": errors, "policy_hash": policy_hash or None, "selected": selected}


def validate_runtime_admission(runtime: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    packet_report = validate_compiled_packet_workforce(packet)
    errors.extend(f"compiled_packet: {item}" for item in packet_report["errors"])
    packet_policy_hash = packet_report.get("policy_hash")
    expected = packet_report.get("selected") if isinstance(packet_report.get("selected"), dict) else None

    runtime_policy_hash, records = _validate_result_structure(runtime, "$.runtime_admission", errors)
    if runtime.get("overall_decision") != "ALLOW":
        errors.append("$.runtime_admission.overall_decision: ALLOW required before execution")
    if packet_policy_hash and runtime_policy_hash != packet_policy_hash:
        errors.append("$.runtime_admission.policy_identity.policy_hash: differs from compiled packet; recompile/re-admit required")

    matching: list[dict[str, Any]] = []
    if expected is not None:
        for record in records:
            demand = _obj(record, "demand")
            request = _obj(record, "request")
            decision = _obj(record, "decision")
            if decision.get("decision") != "ALLOW":
                continue
            if request.get("route_authorized") is not True:
                continue
            missing_controls = decision.get("missing_controls")
            if not isinstance(missing_controls, list) or missing_controls:
                continue
            required = decision.get("required_controls") if isinstance(decision.get("required_controls"), list) else []
            provided = request.get("provided_controls") if isinstance(request.get("provided_controls"), list) else []
            if not set(map(str, required)).issubset(set(map(str, provided))):
                continue
            observed = _record_semantics(record)
            semantic_keys = ("worker_id", "provider", "model_id", "workforce_role", "autonomy", "context_class", "execution_channel", "mutation_intent")
            request_checks = {
                "requested_worker_id": expected.get("worker_id"),
                "provider": expected.get("provider"),
                "model": expected.get("model_id"),
                "role": expected.get("workforce_role"),
                "autonomy": expected.get("autonomy"),
                "context": expected.get("context_class"),
            }
            demand_checks = {
                "execution_channel": expected.get("execution_channel"),
                "requested_role": expected.get("workforce_role"),
                "minimum_autonomy": expected.get("autonomy"),
                "context_class": expected.get("context_class"),
                "mutation_intent": expected.get("mutation_intent"),
                "route_authority": ROUTE_AUTHORITY,
            }
            decision_checks = {
                "resolved_worker_id": expected.get("worker_id"),
                "resolved_provider": expected.get("provider"),
                "resolved_model": expected.get("model_id"),
                "requested_role": expected.get("workforce_role"),
                "admitted_role": expected.get("workforce_role"),
                "requested_autonomy": expected.get("autonomy"),
                "admitted_autonomy": expected.get("autonomy"),
                "requested_context": expected.get("context_class"),
                "admitted_context": expected.get("context_class"),
                "route_authority": ROUTE_AUTHORITY,
            }
            if not all(request.get(k) == val for k, val in request_checks.items()):
                continue
            if not all(demand.get(k) == val for k, val in demand_checks.items()):
                continue
            if not all(decision.get(k) == val for k, val in decision_checks.items()):
                continue
            if all(observed.get(key) == expected.get(key) for key in semantic_keys):
                if observed.get("request_mutation") == expected.get("mutation_intent"):
                    matching.append(record)
        if len(matching) != 1:
            errors.append("$.runtime_admission.records: exactly one ALLOW record must match compiled worker/provider/model/role/autonomy/context/channel/mutation")

    selected_hash = matching[0].get("binding_hash") if len(matching) == 1 else None
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": [],
        "policy_hash": runtime_policy_hash or None,
        "runtime_binding_hash": selected_hash,
        "worker_id": expected.get("worker_id") if expected else None,
    }


def main() -> int:
    args = parse_args()
    try:
        runtime, runtime_sha = safe_json_file(args.runtime_admission, "runtime_admission")
        packet, packet_sha = safe_json_file(args.compiled_packet, "compiled_packet")
        report = validate_runtime_admission(runtime, packet)
        report["runtime_admission_sha256"] = runtime_sha
        report["compiled_packet_sha256"] = packet_sha
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateKeyError, ValueError) as exc:
        report = {"valid": False, "errors": [str(exc)], "warnings": [], "policy_hash": None, "runtime_binding_hash": None, "worker_id": None}
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    sys.stdout.write(output)
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
