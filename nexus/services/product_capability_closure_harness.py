"""Reusable execution harness for the 34 capability × 2 origin matrix.

The harness owns task identity, timing, raw-receipt persistence, and hash
consistency.  It never fabricates invocation, evidence, observable effects, or
verifier success.  Those fields must come from the supplied production runner
and are classified by :mod:`nexus.services.product_capability_closure`.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from nexus.services.capability_registry import (
    PLANNER_EXECUTION_CONTRACTS,
    project_consumer_execution_mode,
)
from nexus.services.product_capability_closure import (
    PRODUCT_CAPABILITIES,
    expected_resolution_type,
    summarize_origin_matrix,
    verify_product_capability_resolution,
)


TASK_SCHEMA = "nexus.product_capability_closure_task.v1"
RUN_SCHEMA = "nexus.product_capability_closure_run.v1"
MATRIX_SCHEMA = "nexus.product_capability_origin_matrix.v1"


def canonical_payload_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ClosureTaskSpec:
    origin: str
    capability: str
    task_id: str
    expected_resolution: str
    expected_effect: Mapping[str, Any]
    provider_policy: Mapping[str, Any]
    allowed_files: tuple[str, ...]
    timeout_sec: float
    verifier_contract: Mapping[str, Any]
    fixture: Mapping[str, Any]
    consumer_mode: str = ""
    execution_class: str = ""
    consumer_effect: str = ""
    consumer_targets: tuple[str, ...] = ()
    provider_authorization_required: bool = False
    contract_source: str = "PLANNER_EXECUTION_CONTRACTS"
    schema: str = TASK_SCHEMA
    public_claim_allowed: bool = False

    def unsigned_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["allowed_files"] = list(self.allowed_files)
        payload["consumer_targets"] = list(self.consumer_targets)
        return payload

    @property
    def spec_hash(self) -> str:
        return canonical_payload_hash(self.unsigned_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_payload(), "spec_hash": self.spec_hash}


def _task_fixture(
    *, capability: str, origin: str, workspace_root: Path
) -> dict[str, Any]:
    task_id = f"closure-{origin}-{capability}"
    statement = (
        f"Execute and verify PRODUCT capability {capability} from {origin} origin "
        "on the existing Nexus mainchain."
    )
    source_hash = hashlib.sha256(b"nexus-product-closure-target-v1").hexdigest()
    route_uses_online = capability not in {"local_model_executor", "repair_loop"} or origin == "online"
    codeintel = {
        "workspace_root": str(workspace_root),
        "target_file": "target.py",
        "target_symbol": "closure_target",
        "scan_report_present": True,
        "impact_report_present": True,
        "risk_score": 1,
        "impacted_files_count": 1,
        "verify_commands": ["python -m py_compile target.py"],
        "verify_timeout_sec": 30,
        "search_query": f"physical evidence for {capability}",
        "search_table": "policy",
        "search_limit": 3,
        "jit_all_tools": ["read_file", "run_test", "write_file"],
        "jit_token_usage": 120,
        "mempalace_tenant_id": "product-closure",
        "mempalace_artifact_type": "capability_evidence",
        "mempalace_artifact": {
            "artifact_id": f"closure-evidence-{capability}",
            "content": f"physical closure evidence for {capability}",
            "source_hash": source_hash,
        },
        "mempalace_query": f"closure-evidence-{capability}",
        "sandbox_command": [
            "python",
            "-c",
            "from pathlib import Path; assert Path('target.py').exists()",
        ],
        "sandbox_timeout_sec": 30,
        "intent_pass": True,
        "target_files": ["target.py"],
        "impact_map": {"target.py": []},
        "acceptance_criteria": ["isolated verifier passes"],
        "deliverables": ["structured capability receipt"],
        "steps": ["execute", "verify", "seal receipt"],
        "handoff_readiness": 1.0,
        "asi_failure_records": [
            {
                "status": "discard",
                "family": "repeated_verifier_failure",
                "rollback_reason": "same verifier mismatch",
                "evidence": f"asi:{task_id}:1",
                "run_id": f"{task_id}:1",
            },
            {
                "status": "discard",
                "family": "repeated_verifier_failure",
                "rollback_reason": "same verifier mismatch",
                "evidence": f"asi:{task_id}:2",
                "run_id": f"{task_id}:2",
            },
        ],
        "forecast_roi_score": 0.9,
        "forecast_tokens": 1000,
        "forecast_reject_prob": 0.05,
        "formal_judge_votes": [{"judge": "deterministic", "verdict": "PASS"}],
        "formal_verification": [
            {"status": "PASS", "evidence": f"isolated-verifier:{task_id}"}
        ],
        "formal_route_receipts": [
            {"route": "mainchain", "evidence_present": True, "gate_passed": True}
        ],
        "meta_opt_episode": {
            "task_id": task_id,
            "task_type": "codeintel",
            "task_desc": statement,
            "solved": True,
            "wall_duration_sec": 0.1,
            "total_tokens_used": 0,
            "trust_mismatch": False,
            "receipts": [
                {
                    "name": capability,
                    "invoked": True,
                    "gate_passed": True,
                    "outcome_contributed": True,
                }
            ],
        },
    }
    fixture: dict[str, Any] = {
        "task_id": task_id,
        "task_statement": statement,
        "task_type": "codeintel",
        "workspace_root": str(workspace_root),
        "route": {
            "recommended_flow": "direct",
            "mainchain_entry": True,
            "origin": origin,
            "online_policy": "auto" if route_uses_online else "deny",
            "escalate": True,
            "escalate_triggered": True,
        },
        "planner": {
            "force_capability": capability,
            "expected_selected_capabilities": [capability],
        },
        "escalate_triggered": True,
        "triggered_escalations": [capability],
        "executor_flags": {capability: True, f"enable_{capability}": True},
        "codeintel": codeintel,
        "pillars": {
            "semantic_status": "VERIFIED",
            "completion_status": "COMPLETE",
            "source_hash": source_hash,
            "intent_pass": True,
            "owner_approved": True,
            "candidate_hash_matches_applied": True,
            "candidate_target_file": "target.py",
        },
        "claim_boundary": {"public_claim_allowed": False},
        "route_surface_changed": False,
    }
    if capability in {"local_model_executor", "repair_loop"}:
        fixture["local_request"] = {
            "schema": "nexus.local_assist.request.v1",
            "task_id": task_id,
            "parent_task_id": task_id,
            "workspace_root": str(workspace_root),
            "task_statement": statement,
            "action": "verified-subtask" if capability == "repair_loop" else "candidate",
            "allowed_files": ["target.py"],
            "target_file": "target.py",
            "target_symbol": "closure_target",
            "verifier_command": ["python", "-m", "py_compile", "target.py"],
            "mutation_policy": "isolated_only",
            "planner_snapshot": {
                "route_truth_source": "CapabilityPlanner",
                "selected_capabilities": [capability],
                "model_call_allowed": True,
                "fallback_policy": "online_continue_fail_closed",
            },
        }
    elif origin == "local":
        fixture["assist_contract"] = {
            "schema": "nexus.verified_assist_packet.v1",
            "producer_verification_required": True,
            "consumption_required": True,
            "final_result_lineage_required": True,
            "raw_cot_allowed": False,
            "raw_patch_allowed": False,
        }
    return fixture


def build_product_task_catalog(workspace_root: str | Path) -> tuple[ClosureTaskSpec, ...]:
    """Build the frozen 68 task specifications from the Planner contract SSOT."""

    root = Path(workspace_root).resolve()
    tasks: list[ClosureTaskSpec] = []
    for origin in ("online", "local"):
        for capability in PRODUCT_CAPABILITIES:
            contract = PLANNER_EXECUTION_CONTRACTS[capability]
            resolution = expected_resolution_type(origin, capability)
            consumer_mode = project_consumer_execution_mode(capability, origin)
            resolution_provider = "local" if capability in {"local_model_executor", "repair_loop"} else "online"
            tasks.append(
                ClosureTaskSpec(
                    origin=origin,
                    capability=capability,
                    task_id=f"closure-{origin}-{capability}",
                    expected_resolution=resolution,
                    consumer_mode=consumer_mode,
                    execution_class=str(contract["execution_class"]),
                    consumer_effect=str(contract["consumer_effect"]),
                    consumer_targets=tuple(contract.get("consumer_targets", ())),
                    provider_authorization_required=bool(contract.get("provider_authorization_required", False)),
                    contract_source="PLANNER_EXECUTION_CONTRACTS",
                    expected_effect={
                        "consumer_effect": contract["consumer_effect"],
                        "success_predicate": contract["success_predicate"],
                        "required_outcome_fields": list(contract["required_outcome_fields"]),
                        "required_evidence_fields": list(contract["required_evidence_fields"]),
                        "physical_callable": contract["physical_callable"],
                        "trigger_policy": contract["trigger_policy"],
                    },
                    provider_policy={
                        "origin_provider": origin,
                        "resolution_provider": resolution_provider,
                        "external_authorization_required": bool(
                            contract["provider_authorization_required"]
                        ),
                        "fixture_allowed": False,
                        "fallback": "fail_closed",
                    },
                    allowed_files=("target.py",),
                    timeout_sec=30.0,
                    verifier_contract={
                        "verifier_id": "closure_target_py_compile",
                        "command": ["python", "-m", "py_compile", "target.py"],
                        "artifact_hash_required": True,
                        "evidence_hash_required": True,
                    },
                    fixture=_task_fixture(
                        capability=capability,
                        origin=origin,
                        workspace_root=root,
                    ),
                )
            )
    return tuple(tasks)


def validate_task_catalog(tasks: Iterable[ClosureTaskSpec]) -> list[str]:
    rows = list(tasks)
    errors: list[str] = []
    expected = {
        (origin, capability)
        for origin in ("online", "local")
        for capability in PRODUCT_CAPABILITIES
    }
    keys = [(task.origin, task.capability) for task in rows]
    if len(rows) != 68:
        errors.append(f"task_count:{len(rows)}")
    if len(set(keys)) != len(keys):
        errors.append("duplicate_origin_capability")
    missing = expected - set(keys)
    if missing:
        errors.extend(f"missing:{origin}:{capability}" for origin, capability in sorted(missing))
    task_ids = [task.task_id for task in rows]
    if len(set(task_ids)) != len(task_ids):
        errors.append("duplicate_task_id")
    for task in rows:
        prefix = f"{task.origin}:{task.capability}"
        if task.schema != TASK_SCHEMA:
            errors.append(f"{prefix}:schema")
        if task.expected_resolution != expected_resolution_type(task.origin, task.capability):
            errors.append(f"{prefix}:resolution")
        if not task.allowed_files:
            errors.append(f"{prefix}:allowed_files")
        if task.timeout_sec <= 0:
            errors.append(f"{prefix}:timeout")
        if not task.expected_effect.get("success_predicate"):
            errors.append(f"{prefix}:expected_effect")
        if not task.verifier_contract.get("command"):
            errors.append(f"{prefix}:verifier")
        if task.provider_policy.get("fixture_allowed") is not False:
            errors.append(f"{prefix}:fixture_policy")
        fixture = task.fixture
        route = fixture.get("route") if isinstance(fixture.get("route"), Mapping) else {}
        flags = fixture.get("executor_flags") if isinstance(fixture.get("executor_flags"), Mapping) else {}
        triggered = fixture.get("triggered_escalations") or []
        policy = str(task.expected_effect.get("trigger_policy") or "")
        if policy.startswith("escalate") or policy.startswith("triggered"):
            if not route.get("escalate_triggered") or not flags.get(task.capability) or task.capability not in triggered:
                errors.append(f"{prefix}:trigger_not_armed")
    return errors


ClosureRunner = Callable[[ClosureTaskSpec], Mapping[str, Any]]


def _identity_errors(task: ClosureTaskSpec, raw: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = {
        "task_id": task.task_id,
        "origin": task.origin,
        "capability": task.capability,
        "resolution_type": task.expected_resolution,
    }
    for field, value in expected.items():
        if field not in raw:
            errors.append(f"missing_{field}")
        elif str(raw.get(field)) != value:
            errors.append(f"{field}_mismatch")
    if not str(raw.get("planner_decision_id") or "").strip():
        errors.append("missing_planner_decision_id")
    if raw.get("route_surface_changed") is not False:
        errors.append("route_surface_not_frozen")
    if raw.get("public_claim_allowed") is not False:
        errors.append("claim_boundary_not_fail_closed")
    return errors


def run_closure_task(
    task: ClosureTaskSpec,
    runner: ClosureRunner,
    *,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Run one cell and return a fail-closed, hash-bound harness row."""

    task_errors = validate_task_catalog([task])
    # Single-cell validation intentionally ignores the global task-count error.
    task_errors = [error for error in task_errors if error.startswith(f"{task.origin}:{task.capability}")]
    if task_errors:
        raise ValueError("invalid closure task: " + ",".join(task_errors))

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    run_id = f"closure-{uuid.uuid4().hex}"
    started_at = _utc_now()
    started_ns = time.perf_counter_ns()
    runner_error = ""
    try:
        produced = runner(task)
        raw = dict(produced) if isinstance(produced, Mapping) else {}
        if not isinstance(produced, Mapping):
            runner_error = "runner_returned_non_mapping"
    except Exception as exc:  # fail closed and preserve the exception class only
        raw = {}
        runner_error = f"runner_exception:{type(exc).__name__}"
    finished_ns = time.perf_counter_ns()
    finished_at = _utc_now()

    raw_receipt_path = root / f"{run_id}.raw_receipt.json"
    raw_receipt_path.write_text(
        json.dumps(raw, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    raw_receipt_hash = canonical_payload_hash(raw)
    consistency_errors = _identity_errors(task, raw)
    if runner_error:
        consistency_errors.append(runner_error)

    record = dict(raw)
    record.update(
        {
            "run_id": run_id,
            "task_id": task.task_id,
            "origin": task.origin,
            "capability": task.capability,
            "resolution_type": task.expected_resolution,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": round((finished_ns - started_ns) / 1_000_000, 3),
            "receipt_path": str(raw_receipt_path),
            "receipt_payload": raw,
            "receipt_hash": raw_receipt_hash,
            "receipt_hash_verified": True,
            "harness_consistency_errors": consistency_errors,
            "public_claim_allowed": False,
        }
    )
    verdict = verify_product_capability_resolution(record)
    result = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "task_spec_hash": task.spec_hash,
        "origin": task.origin,
        "capability": task.capability,
        "task_id": task.task_id,
        "planner_decision_id": str(raw.get("planner_decision_id") or ""),
        "selected_capability": task.capability,
        "trigger_condition": bool(raw.get("trigger_condition_met")),
        "resolution_type": task.expected_resolution,
        "handler_or_stage_callsite": str(raw.get("physical_callable") or ""),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": record["duration_ms"],
        "provider": str(raw.get("provider") or ""),
        "model": str(raw.get("model") or ""),
        "model_called": bool(_nested(raw, "local_execution", "model_called")),
        "network_invoked": bool(
            raw.get("network_invoked")
            or _nested(raw, "local_execution", "network_invoked")
        ),
        "raw_receipt_path": str(raw_receipt_path),
        "receipt_hash": raw_receipt_hash,
        "structured_evidence_refs": list(raw.get("evidence_refs") or []),
        "artifact_hash": str(_nested(raw, "observable_effect", "artifact_hash") or ""),
        "candidate_hash": str(_nested(raw, "local_execution", "candidate_hash") or ""),
        "verifier_id": str(_nested(raw, "verifier", "id") or ""),
        "verifier_result": bool(_nested(raw, "verifier", "passed")),
        "verifier_evidence_hash": str(_nested(raw, "verifier", "evidence_hash") or ""),
        "terminal_status": str(raw.get("status") or ""),
        "closure_verdict": verdict,
        "claim_boundary": {"public_claim_allowed": False},
        "harness_consistency_errors": consistency_errors,
        "record": record,
        "public_claim_allowed": False,
    }
    result["run_hash"] = canonical_payload_hash(result)
    return result


def _nested(value: Mapping[str, Any], parent: str, child: str) -> Any:
    item = value.get(parent)
    return item.get(child) if isinstance(item, Mapping) else None


def run_origin_capability_matrix(
    tasks: Iterable[ClosureTaskSpec],
    runner: ClosureRunner,
    *,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Run an exact 68-cell catalog and persist one hash-bound matrix receipt."""

    catalog = tuple(tasks)
    errors = validate_task_catalog(catalog)
    if errors:
        raise ValueError("invalid closure task catalog: " + ",".join(errors))
    rows = [run_closure_task(task, runner, output_dir=output_dir) for task in catalog]
    summary = summarize_origin_matrix(row["record"] for row in rows)
    matrix_path = Path(output_dir) / "nexus_product_capability_origin_matrix.json"
    payload: dict[str, Any] = {
        "schema": MATRIX_SCHEMA,
        "generated_at": _utc_now(),
        "catalog_hash": canonical_payload_hash([task.to_dict() for task in catalog]),
        "task_count": len(catalog),
        "rows": rows,
        "summary": summary,
        "route_surface_changed": any(
            bool(row["record"].get("route_surface_changed")) for row in rows
        ),
        "matrix_path": str(matrix_path),
        "public_claim_allowed": False,
    }
    payload["matrix_hash"] = canonical_payload_hash(payload)
    matrix_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return payload


def payload_hash_matches(payload: Mapping[str, Any], hash_field: str) -> bool:
    """Recompute a self-hash while excluding the named hash field."""

    claimed = str(payload.get(hash_field) or "")
    unsigned = {key: value for key, value in payload.items() if key != hash_field}
    return bool(claimed) and canonical_payload_hash(unsigned) == claimed
