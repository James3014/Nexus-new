from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from nexus.contracts.context_budget import build_context_budget_receipt, validate_context_budget_receipt


CONTEXT_ASSEMBLY_CONTRACT_SCHEMA = "nexus.context_assembly_contract.v1"
SOURCE_MATERIALIZATION_MODES = frozenset(
    {
        "NO_SOURCE",
        "DIRECT_SLICE",
        "REDUCED_CAPSULE",
        "RAW_SOURCE",
    }
)

_PACKAGE_HASH_FIELDS = (
    "schema",
    "task_id",
    "attempt_id",
    "context_policy",
    "planner_decision_id",
    "planner_plan_hash",
    "selected_capability_ids",
    "source_mode",
    "source_provenance_refs",
    "consumer_role",
    "consumer_channel",
    "worker_binding",
    "receipt",
)


@dataclass(frozen=True)
class ContextAssemblyContract:
    task_id: str
    receipt: Mapping[str, Any]
    context_policy: str = "preserve_l0_l1_hard_budget"
    attempt_id: str = ""
    planner_decision_id: str = ""
    planner_plan_hash: str = ""
    selected_capability_ids: tuple[str, ...] = ()
    source_mode: str = "NO_SOURCE"
    source_provenance_refs: tuple[Mapping[str, Any], ...] = ()
    consumer_role: str = ""
    consumer_channel: str = ""
    worker_binding: Mapping[str, str] = field(default_factory=dict)
    schema: str = CONTEXT_ASSEMBLY_CONTRACT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        selected_capability_ids = _normalize_ids(self.selected_capability_ids)
        source_provenance_refs = [dict(item) for item in self.source_provenance_refs]
        worker_binding = {str(key): str(value) for key, value in self.worker_binding.items()}
        payload: dict[str, Any] = {
            "schema": self.schema,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "context_policy": self.context_policy,
            "planner_decision_id": self.planner_decision_id,
            "planner_plan_hash": self.planner_plan_hash,
            "selected_capability_ids": selected_capability_ids,
            "source_mode": str(self.source_mode or "NO_SOURCE").strip().upper(),
            "source_provenance_refs": source_provenance_refs,
            "consumer_role": self.consumer_role,
            "consumer_channel": self.consumer_channel,
            "worker_binding": worker_binding,
            "receipt": dict(self.receipt),
        }
        payload["package_hash"] = _context_package_hash(payload)
        blockers = validate_context_assembly_contract(payload)
        materialized_source_ids = _receipt_source_ids(payload["receipt"], key="kept_sources")
        dropped_source_ids = _receipt_source_ids(payload["receipt"], key="dropped_sources")
        planner_binding_status = _planner_binding_status(payload)
        payload.update(
            {
                "status": "PASS" if not blockers else "RETURN",
                "kept_source_count": len(materialized_source_ids),
                "dropped_source_count": len(dropped_source_ids),
                "preserved_L0_L1": bool(self.receipt.get("preserved_L0_L1", False)),
                "materialized_source_ids": materialized_source_ids,
                "dropped_source_ids": dropped_source_ids,
                "planner_binding_status": planner_binding_status,
                "selection_state": "SELECTED" if selected_capability_ids else "NO_SELECTED_CONTEXT",
                "materialization_state": (
                    "MATERIALIZED" if materialized_source_ids else "NO_MATERIALIZED_CONTEXT"
                ),
                "serialization_state": "NOT_BOUND",
                "physical_consumption_state": "NOT_PROVEN",
                "outcome_contribution_state": "NOT_PROVEN",
                "blockers": blockers,
                "claim_boundary": [
                    "Context assembly contracts materialize already-selected context under budget only.",
                    "They do not decide route dispatch, capability selection, worker eligibility, runtime promotion, or public readiness.",
                    "Package construction does not prove provider serialization, physical consumption, or outcome contribution.",
                    "Source/provenance references preserve their existing claim ceilings and do not strengthen source_hash or claim_verified semantics.",
                ],
            }
        )
        return payload


def build_context_assembly_contract(
    *,
    task_id: str,
    sources: list[Mapping[str, Any]],
    token_budget: int,
    context_policy: str = "preserve_l0_l1_hard_budget",
    attempt_id: str = "",
    planner_decision_id: str = "",
    planner_plan_hash: str = "",
    selected_capability_ids: Sequence[str] = (),
    source_mode: str = "NO_SOURCE",
    source_provenance_refs: Sequence[Mapping[str, Any]] = (),
    consumer_role: str = "",
    consumer_channel: str = "",
    worker_binding: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    receipt = build_context_budget_receipt(sources, token_budget=token_budget).to_dict()
    return ContextAssemblyContract(
        task_id=task_id,
        receipt=receipt,
        context_policy=context_policy,
        attempt_id=attempt_id,
        planner_decision_id=planner_decision_id,
        planner_plan_hash=planner_plan_hash,
        selected_capability_ids=tuple(selected_capability_ids),
        source_mode=source_mode,
        source_provenance_refs=tuple(source_provenance_refs),
        consumer_role=consumer_role,
        consumer_channel=consumer_channel,
        worker_binding=dict(worker_binding or {}),
    ).to_dict()


def validate_context_assembly_contract(payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != CONTEXT_ASSEMBLY_CONTRACT_SCHEMA:
        blockers.append("invalid_context_assembly_schema")
    if not str(payload.get("task_id") or "").strip():
        blockers.append("missing_task_id")

    receipt = payload.get("receipt")
    if not isinstance(receipt, Mapping):
        blockers.append("missing_context_budget_receipt")
        return sorted(set(blockers))
    blockers.extend(f"receipt:{item}" for item in validate_context_budget_receipt(receipt))
    if str(receipt.get("status") or "").upper() != "PASS":
        blockers.append("receipt_not_pass")

    selected_capability_ids = _normalize_ids(payload.get("selected_capability_ids", ()) or ())
    planner_decision_id = str(payload.get("planner_decision_id") or "").strip()
    planner_plan_hash = str(payload.get("planner_plan_hash") or "").strip()
    if selected_capability_ids and not planner_decision_id:
        blockers.append("selected_context_missing_planner_decision_id")
    if selected_capability_ids and not planner_plan_hash:
        blockers.append("selected_context_missing_planner_plan_hash")

    source_mode = str(payload.get("source_mode") or "NO_SOURCE").strip().upper()
    if source_mode not in SOURCE_MATERIALIZATION_MODES:
        blockers.append("invalid_source_materialization_mode")
    source_refs = payload.get("source_provenance_refs", ()) or ()
    if not isinstance(source_refs, (list, tuple)):
        blockers.append("invalid_source_provenance_refs")
        source_refs = ()
    if source_mode == "NO_SOURCE" and source_refs:
        blockers.append("source_refs_with_no_source_mode")
    if source_mode in SOURCE_MATERIALIZATION_MODES - {"NO_SOURCE"} and not source_refs:
        blockers.append("source_mode_missing_provenance_refs")
    for index, reference in enumerate(source_refs):
        if not isinstance(reference, Mapping):
            blockers.append(f"invalid_source_provenance_ref:{index}")
            continue
        for key in ("repository", "revision", "path"):
            if not str(reference.get(key) or "").strip():
                blockers.append(f"source_provenance_ref_missing_{key}:{index}")

    consumer_role = str(payload.get("consumer_role") or "").strip()
    consumer_channel = str(payload.get("consumer_channel") or "").strip()
    if bool(consumer_role) != bool(consumer_channel):
        blockers.append("incomplete_consumer_binding")

    worker_binding = payload.get("worker_binding", {}) or {}
    if not isinstance(worker_binding, Mapping):
        blockers.append("invalid_worker_binding")
    elif worker_binding:
        for key in ("worker_id", "provider", "model"):
            if not str(worker_binding.get(key) or "").strip():
                blockers.append(f"incomplete_worker_binding:{key}")

    observed_package_hash = str(payload.get("package_hash") or "").strip()
    if observed_package_hash and observed_package_hash != _context_package_hash(payload):
        blockers.append("context_package_hash_mismatch")

    for source in _receipt_sources(receipt):
        tier = str(source.get("metadata", {}).get("skill_tier") or "").strip().lower()
        source_id = str(source.get("source_id") or "")
        if _is_quarantined_skill_source(source_id=source_id, tier=tier):
            blockers.append(f"quarantined_skill_context:{source_id}")
    if bool(payload.get("runtime_update_allowed", False)):
        blockers.append("context_assembly_must_not_update_runtime")
    if bool(payload.get("public_benchmark_allowed", False)):
        blockers.append("context_assembly_must_not_unlock_public_benchmark")
    return sorted(set(blockers))


def _receipt_sources(receipt: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    sources: list[Mapping[str, Any]] = []
    for key in ("kept_sources", "dropped_sources"):
        for source in receipt.get(key, []) or []:
            if isinstance(source, Mapping):
                sources.append(source)
    return sources


def _receipt_source_ids(receipt: Mapping[str, Any], *, key: str) -> list[str]:
    return sorted(
        {
            str(source.get("source_id") or "").strip()
            for source in receipt.get(key, []) or []
            if isinstance(source, Mapping) and str(source.get("source_id") or "").strip()
        }
    )


def _normalize_ids(values: Sequence[Any]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _planner_binding_status(payload: Mapping[str, Any]) -> str:
    decision_id = str(payload.get("planner_decision_id") or "").strip()
    plan_hash = str(payload.get("planner_plan_hash") or "").strip()
    if decision_id and plan_hash:
        return "BOUND"
    if decision_id or plan_hash or payload.get("selected_capability_ids"):
        return "INCOMPLETE"
    return "NOT_APPLICABLE"


def _context_package_hash(payload: Mapping[str, Any]) -> str:
    basis = {
        key: _canonical_json_value(payload.get(key))
        for key in _PACKAGE_HASH_FIELDS
    }
    encoded = json.dumps(basis, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _is_quarantined_skill_source(*, source_id: str, tier: str) -> bool:
    lowered = source_id.lower()
    if tier in {"nexus_curated", "nexuscuratedcandidate", "curated"}:
        return False
    if tier in {"candidate_inbox", "generated_candidate", "vendor", "archive", "quarantine", "worktree_copy"}:
        return True
    return any(marker in lowered for marker in ("candidate-skill-from-", "auto-gen-", ".codex/worktrees"))
