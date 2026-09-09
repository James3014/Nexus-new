from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

from nexus.contracts.context_budget import build_context_budget_receipt, validate_context_budget_receipt


CONTEXT_ASSEMBLY_CONTRACT_SCHEMA = "nexus.context_assembly_contract.v1"
SOURCE_MATERIALIZATION_MODES = frozenset(
    {"NO_SOURCE", "DIRECT_SLICE", "REDUCED_CAPSULE", "RAW_SOURCE"}
)


@dataclass(frozen=True)
class ContextAssemblyContract:
    task_id: str
    receipt: Mapping[str, Any]
    context_policy: str = "preserve_l0_l1_hard_budget"
    attempt_id: str = ""
    planner_decision_id: str = ""
    plan_hash: str = ""
    selected_capabilities: tuple[str, ...] = ()
    materialized_evidence_ids: tuple[str, ...] = ()
    serialized_evidence_ids: tuple[str, ...] = ()
    source_materialization: Mapping[str, Any] | None = None
    consumer_role: str = ""
    consumer_channel: str = ""
    worker_binding: Mapping[str, Any] | None = None
    schema: str = CONTEXT_ASSEMBLY_CONTRACT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": self.schema,
            "task_id": self.task_id,
            "context_policy": self.context_policy,
            "receipt": dict(self.receipt),
            "selected_capabilities": list(self.selected_capabilities),
            "materialized_evidence_ids": list(self.materialized_evidence_ids),
            "serialized_evidence_ids": list(self.serialized_evidence_ids),
        }
        if self.attempt_id:
            payload["attempt_id"] = self.attempt_id
        if self.planner_decision_id:
            payload["planner_decision_id"] = self.planner_decision_id
        if self.plan_hash:
            payload["plan_hash"] = self.plan_hash
        if self.source_materialization is not None:
            payload["source_materialization"] = dict(self.source_materialization)
        if self.consumer_role:
            payload["consumer_role"] = self.consumer_role
        if self.consumer_channel:
            payload["consumer_channel"] = self.consumer_channel
        if self.worker_binding is not None:
            payload["worker_binding"] = dict(self.worker_binding)

        blockers = validate_context_assembly_contract(payload)
        result = {
            **payload,
            "status": "PASS" if not blockers else "RETURN",
            "kept_source_count": len(self.receipt.get("kept_sources", []) or []),
            "dropped_source_count": len(self.receipt.get("dropped_sources", []) or []),
            "preserved_L0_L1": bool(self.receipt.get("preserved_L0_L1", False)),
            "blockers": blockers,
            "claim_boundary": [
                "Context assembly materializes already-selected context under budget only.",
                "selected != materialized != serialized != physically_consumed != outcome_contributed.",
                "The contract does not decide route, capability selection, worker/provider/model selection, verification, or public readiness.",
            ],
        }
        result["package_hash"] = compute_context_assembly_package_hash(result)
        return result


def build_context_assembly_contract(
    *,
    task_id: str,
    sources: list[Mapping[str, Any]],
    token_budget: int,
    context_policy: str = "preserve_l0_l1_hard_budget",
    attempt_id: str = "",
    planner_decision_id: str = "",
    plan_hash: str = "",
    selected_capabilities: list[str] | tuple[str, ...] | None = None,
    materialized_evidence_ids: list[str] | tuple[str, ...] | None = None,
    serialized_evidence_ids: list[str] | tuple[str, ...] | None = None,
    source_materialization: Mapping[str, Any] | None = None,
    consumer_role: str = "",
    consumer_channel: str = "",
    worker_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    receipt = build_context_budget_receipt(sources, token_budget=token_budget).to_dict()
    return ContextAssemblyContract(
        task_id=task_id,
        receipt=receipt,
        context_policy=context_policy,
        attempt_id=attempt_id,
        planner_decision_id=planner_decision_id,
        plan_hash=plan_hash,
        selected_capabilities=_normalized_id_tuple(selected_capabilities),
        materialized_evidence_ids=_normalized_id_tuple(materialized_evidence_ids),
        serialized_evidence_ids=_normalized_id_tuple(serialized_evidence_ids),
        source_materialization=source_materialization,
        consumer_role=consumer_role,
        consumer_channel=consumer_channel,
        worker_binding=worker_binding,
    ).to_dict()


def compute_context_assembly_package_hash(payload: Mapping[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in payload.items()
        if key not in {"package_hash", "blockers", "status"}
    }
    return sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


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

    for source in _receipt_sources(receipt):
        tier = str(source.get("metadata", {}).get("skill_tier") or "").strip().lower()
        source_id = str(source.get("source_id") or "")
        if _is_quarantined_skill_source(source_id=source_id, tier=tier):
            blockers.append(f"quarantined_skill_context:{source_id}")

    selected = set(_normalized_id_tuple(payload.get("selected_capabilities")))
    materialized = set(_normalized_id_tuple(payload.get("materialized_evidence_ids")))
    serialized = set(_normalized_id_tuple(payload.get("serialized_evidence_ids")))
    if serialized - materialized:
        blockers.append("serialized_evidence_not_materialized")

    source_materialization = payload.get("source_materialization")
    if source_materialization is not None:
        if not isinstance(source_materialization, Mapping):
            blockers.append("invalid_source_materialization")
        else:
            mode = str(source_materialization.get("mode") or "").strip().upper()
            if mode not in SOURCE_MATERIALIZATION_MODES:
                blockers.append("invalid_source_materialization_mode")
            if mode == "NO_SOURCE" and any(
                source_materialization.get(key)
                for key in ("path", "ranges", "source_hash", "content_hash", "reduced_context")
            ):
                blockers.append("no_source_mode_contains_source_payload")
            if mode in {"DIRECT_SLICE", "REDUCED_CAPSULE", "RAW_SOURCE"}:
                if not str(source_materialization.get("revision") or "").strip():
                    blockers.append("source_materialization_missing_revision")
                if not str(source_materialization.get("path") or "").strip():
                    blockers.append("source_materialization_missing_path")
            if mode == "REDUCED_CAPSULE" and "uncertainties" not in source_materialization:
                blockers.append("reduced_capsule_missing_uncertainties")

    worker_binding = payload.get("worker_binding")
    if worker_binding is not None and not isinstance(worker_binding, Mapping):
        blockers.append("invalid_worker_binding")

    if bool(payload.get("runtime_update_allowed", False)):
        blockers.append("context_assembly_must_not_update_runtime")
    if bool(payload.get("public_benchmark_allowed", False)):
        blockers.append("context_assembly_must_not_unlock_public_benchmark")
    if bool(payload.get("physically_consumed", False)):
        blockers.append("context_assembly_must_not_self_attest_physical_consumption")
    if bool(payload.get("outcome_contributed", False)):
        blockers.append("context_assembly_must_not_self_attest_outcome_contribution")

    # Selection identity is preserved as an input projection only; this contract must
    # never treat materialization as authority to add Planner capabilities.
    if selected and not all(item.strip() for item in selected):
        blockers.append("invalid_selected_capability_identity")

    return sorted(set(blockers))


def _normalized_id_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    else:
        try:
            values = list(value)
        except TypeError:
            return ()
    return tuple(sorted({str(item).strip() for item in values if str(item).strip()}))


def _receipt_sources(receipt: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    sources: list[Mapping[str, Any]] = []
    for key in ("kept_sources", "dropped_sources"):
        for source in receipt.get(key, []) or []:
            if isinstance(source, Mapping):
                sources.append(source)
    return sources


def _is_quarantined_skill_source(*, source_id: str, tier: str) -> bool:
    lowered = source_id.lower()
    if tier in {"nexus_curated", "nexuscuratedcandidate", "curated"}:
        return False
    if tier in {"candidate_inbox", "generated_candidate", "vendor", "archive", "quarantine", "worktree_copy"}:
        return True
    return any(marker in lowered for marker in ("candidate-skill-from-", "auto-gen-", ".codex/worktrees"))
