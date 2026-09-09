from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from nexus.contracts.context_budget import build_context_budget_receipt, validate_context_budget_receipt
from nexus.contracts.source_materialization import validate_source_materialization_projection


CONTEXT_ASSEMBLY_CONTRACT_SCHEMA = "nexus.context_assembly_contract.v1"


@dataclass(frozen=True)
class ContextAssemblyContract:
    task_id: str
    receipt: Mapping[str, Any]
    context_policy: str = "preserve_l0_l1_hard_budget"
    planner_decision_id: str = ""
    plan_hash: str = ""
    selected_capabilities: tuple[str, ...] = ()
    serialized_evidence_ids: tuple[str, ...] = ()
    source_materialization: Mapping[str, Any] = field(default_factory=dict)
    consumer: Mapping[str, Any] = field(default_factory=dict)
    schema: str = CONTEXT_ASSEMBLY_CONTRACT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": self.schema,
            "task_id": self.task_id,
            "context_policy": self.context_policy,
            "receipt": dict(self.receipt),
            "planner_decision_id": self.planner_decision_id,
            "plan_hash": self.plan_hash,
            "selected_capabilities": list(self.selected_capabilities),
            "serialized_evidence_ids": list(self.serialized_evidence_ids),
            "source_materialization": dict(self.source_materialization),
            "consumer": dict(self.consumer),
        }
        payload["package_hash"] = _hash_context_assembly(payload)
        blockers = validate_context_assembly_contract(payload)
        source_materialization = payload["source_materialization"]
        selected_sources = (
            source_materialization.get("selected_sources", [])
            if isinstance(source_materialization, Mapping)
            else []
        )
        return {
            **payload,
            "status": "PASS" if not blockers else "RETURN",
            "kept_source_count": len(self.receipt.get("kept_sources", []) or []),
            "dropped_source_count": len(self.receipt.get("dropped_sources", []) or []),
            "preserved_L0_L1": bool(self.receipt.get("preserved_L0_L1", False)),
            "materialized_source_count": len(selected_sources or []),
            "serialized_evidence_count": len(self.serialized_evidence_ids),
            "blockers": blockers,
            "claim_boundary": [
                "Context assembly records bounded selected/materialized/serialized context only.",
                "Physical consumption and outcome contribution require downstream evidence.",
                "Context assembly does not decide route, provider, model, runtime promotion, or public readiness.",
            ],
        }


def build_context_assembly_contract(
    *,
    task_id: str,
    sources: list[Mapping[str, Any]],
    token_budget: int,
    context_policy: str = "preserve_l0_l1_hard_budget",
    planner_decision_id: str = "",
    plan_hash: str = "",
    selected_capabilities: list[str] | tuple[str, ...] | None = None,
    serialized_evidence_ids: list[str] | tuple[str, ...] | None = None,
    source_materialization: Mapping[str, Any] | None = None,
    consumer: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    receipt = build_context_budget_receipt(sources, token_budget=token_budget).to_dict()
    return ContextAssemblyContract(
        task_id=task_id,
        receipt=receipt,
        context_policy=context_policy,
        planner_decision_id=str(planner_decision_id or "").strip(),
        plan_hash=str(plan_hash or "").strip(),
        selected_capabilities=_normalized_identities(selected_capabilities),
        serialized_evidence_ids=_normalized_identities(serialized_evidence_ids),
        source_materialization=dict(source_materialization or {}),
        consumer=dict(consumer or {}),
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
    for source in _receipt_sources(receipt):
        tier = str(source.get("metadata", {}).get("skill_tier") or "").strip().lower()
        source_id = str(source.get("source_id") or "")
        if _is_quarantined_skill_source(source_id=source_id, tier=tier):
            blockers.append(f"quarantined_skill_context:{source_id}")

    selected_capabilities = payload.get("selected_capabilities", [])
    serialized_evidence_ids = payload.get("serialized_evidence_ids", [])
    source_materialization = payload.get("source_materialization", {})
    consumer = payload.get("consumer", {})
    for field_name, value in (
        ("selected_capabilities", selected_capabilities),
        ("serialized_evidence_ids", serialized_evidence_ids),
    ):
        if not isinstance(value, list) or any(not str(item).strip() for item in value):
            blockers.append(f"{field_name}_malformed")

    if source_materialization and not isinstance(source_materialization, Mapping):
        blockers.append("source_materialization_malformed")
    elif isinstance(source_materialization, Mapping) and source_materialization:
        blockers.extend(
            f"source_materialization:{item}"
            for item in validate_source_materialization_projection(source_materialization)
        )

    if consumer and not isinstance(consumer, Mapping):
        blockers.append("consumer_binding_malformed")

    has_model_context_lineage = bool(
        selected_capabilities
        or serialized_evidence_ids
        or source_materialization
        or consumer
        or str(payload.get("planner_decision_id") or "").strip()
        or str(payload.get("plan_hash") or "").strip()
    )
    if has_model_context_lineage:
        if not str(payload.get("planner_decision_id") or "").strip():
            blockers.append("missing_planner_decision_id")
        if not str(payload.get("plan_hash") or "").strip():
            blockers.append("missing_plan_hash")

    if bool(payload.get("physically_consumed", False)):
        blockers.append("context_assembly_must_not_claim_physical_consumption")
    if bool(payload.get("outcome_contributed", False)):
        blockers.append("context_assembly_must_not_claim_outcome_contribution")
    if bool(payload.get("runtime_update_allowed", False)):
        blockers.append("context_assembly_must_not_update_runtime")
    if bool(payload.get("public_benchmark_allowed", False)):
        blockers.append("context_assembly_must_not_unlock_public_benchmark")

    package_hash = str(payload.get("package_hash") or "")
    if package_hash and package_hash != _hash_context_assembly(payload):
        blockers.append("context_assembly_package_hash_mismatch")
    return sorted(set(blockers))


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


def _normalized_identities(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    normalized = [str(item).strip() for item in (values or ()) if str(item).strip()]
    return tuple(dict.fromkeys(normalized))


def _hash_context_assembly(payload: Mapping[str, Any]) -> str:
    canonical = {
        str(key): value
        for key, value in payload.items()
        if key
        not in {
            "package_hash",
            "status",
            "kept_source_count",
            "dropped_source_count",
            "preserved_L0_L1",
            "materialized_source_count",
            "serialized_evidence_count",
            "blockers",
            "claim_boundary",
        }
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
