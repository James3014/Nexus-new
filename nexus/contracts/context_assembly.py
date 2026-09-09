from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from nexus.contracts.context_budget import build_context_budget_receipt, validate_context_budget_receipt


CONTEXT_ASSEMBLY_CONTRACT_SCHEMA = "nexus.context_assembly_contract.v1"
SOURCE_MATERIALIZATION_MODES = (
    "NO_SOURCE",
    "DIRECT_SLICE",
    "REDUCED_CAPSULE",
    "RAW_SOURCE",
)


@dataclass(frozen=True)
class ContextAssemblyContract:
    task_id: str
    receipt: Mapping[str, Any]
    context_policy: str = "preserve_l0_l1_hard_budget"
    attempt_id: str = ""
    planner_decision_id: str = ""
    planner_plan_id: str = ""
    selected_capability_ids: tuple[str, ...] = ()
    materialized_context_ids: tuple[str, ...] = ()
    serialized_context_ids: tuple[str, ...] = ()
    source_mode: str = "NO_SOURCE"
    source_references: tuple[Mapping[str, Any], ...] = ()
    consumer_role: str = ""
    consumer_channel: str = ""
    worker_binding: Mapping[str, Any] = field(default_factory=dict)
    schema: str = CONTEXT_ASSEMBLY_CONTRACT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": self.schema,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "planner_decision_id": self.planner_decision_id,
            "planner_plan_id": self.planner_plan_id,
            "context_policy": self.context_policy,
            "selected_capability_ids": list(self.selected_capability_ids),
            "materialized_context_ids": list(self.materialized_context_ids),
            "serialized_context_ids": list(self.serialized_context_ids),
            "source_mode": self.source_mode,
            "source_references": [dict(item) for item in self.source_references],
            "consumer_role": self.consumer_role,
            "consumer_channel": self.consumer_channel,
            "worker_binding": dict(self.worker_binding),
            "receipt": dict(self.receipt),
        }
        payload["package_hash"] = _package_hash(payload)
        blockers = validate_context_assembly_contract(payload)
        payload.update(
            {
                "status": "PASS" if not blockers else "RETURN",
                "kept_source_count": len(self.receipt.get("kept_sources", []) or []),
                "dropped_source_count": len(self.receipt.get("dropped_sources", []) or []),
                "preserved_L0_L1": bool(self.receipt.get("preserved_L0_L1", False)),
                "blockers": blockers,
                "claim_boundary": [
                    "Context assembly contracts select context under budget only.",
                    "Materialization is limited to already-selected bounded context; it does not create route or selection authority.",
                    "It does not select capabilities, route, provider, model, verifier, or claim authority.",
                    "selected, materialized, serialized, physically_consumed, and outcome_contributed remain distinct states.",
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
    planner_plan_id: str = "",
    selected_capability_ids: Sequence[str] = (),
    materialized_context_ids: Sequence[str] = (),
    serialized_context_ids: Sequence[str] = (),
    source_mode: str = "NO_SOURCE",
    source_references: Sequence[Mapping[str, Any]] = (),
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
        planner_plan_id=planner_plan_id,
        selected_capability_ids=_string_tuple(selected_capability_ids),
        materialized_context_ids=_string_tuple(materialized_context_ids),
        serialized_context_ids=_string_tuple(serialized_context_ids),
        source_mode=str(source_mode or "NO_SOURCE").strip().upper(),
        source_references=tuple(dict(item) for item in source_references),
        consumer_role=str(consumer_role or "").strip(),
        consumer_channel=str(consumer_channel or "").strip(),
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

    for source in _receipt_sources(receipt):
        tier = str(source.get("metadata", {}).get("skill_tier") or "").strip().lower()
        source_id = str(source.get("source_id") or "")
        if _is_quarantined_skill_source(source_id=source_id, tier=tier):
            blockers.append(f"quarantined_skill_context:{source_id}")

    source_mode = str(payload.get("source_mode") or "NO_SOURCE").strip().upper()
    if source_mode not in SOURCE_MATERIALIZATION_MODES:
        blockers.append("invalid_source_materialization_mode")
    source_references = payload.get("source_references", []) or []
    if not isinstance(source_references, (list, tuple)):
        blockers.append("invalid_source_references")
        source_references = []
    if source_mode == "NO_SOURCE" and source_references:
        blockers.append("no_source_mode_must_not_carry_source_references")
    if source_mode != "NO_SOURCE" and not source_references:
        blockers.append("source_materialization_requires_source_reference")
    for index, reference in enumerate(source_references):
        blockers.extend(_validate_source_reference(index, reference))

    for field_name in (
        "selected_capability_ids",
        "materialized_context_ids",
        "serialized_context_ids",
    ):
        blockers.extend(_validate_identity_sequence(field_name, payload.get(field_name, []) or []))

    package_hash = str(payload.get("package_hash") or "").strip()
    if package_hash and package_hash != _package_hash(payload):
        blockers.append("context_package_hash_mismatch")

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


def _is_quarantined_skill_source(*, source_id: str, tier: str) -> bool:
    lowered = source_id.lower()
    if tier in {"nexus_curated", "nexuscuratedcandidate", "curated"}:
        return False
    if tier in {"candidate_inbox", "generated_candidate", "vendor", "archive", "quarantine", "worktree_copy"}:
        return True
    return any(marker in lowered for marker in ("candidate-skill-from-", "auto-gen-", ".codex/worktrees"))


def _string_tuple(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(str(value).strip() for value in values if str(value).strip())


def _validate_identity_sequence(field_name: str, values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return [f"invalid_{field_name}"]
    normalized = [str(value).strip() for value in values]
    blockers: list[str] = []
    if any(not value for value in normalized):
        blockers.append(f"empty_{field_name}")
    if len(normalized) != len(set(normalized)):
        blockers.append(f"duplicate_{field_name}")
    return blockers


def _validate_source_reference(index: int, reference: Any) -> list[str]:
    prefix = f"source_reference[{index}]"
    if not isinstance(reference, Mapping):
        return [f"{prefix}:invalid_mapping"]
    blockers: list[str] = []
    if not str(reference.get("path") or "").strip():
        blockers.append(f"{prefix}:missing_path")
    if not str(reference.get("claim_ceiling") or "").strip():
        blockers.append(f"{prefix}:missing_claim_ceiling")
    revision = str(reference.get("revision") or "").strip()
    if revision and (len(revision) != 40 or any(ch not in "0123456789abcdefABCDEF" for ch in revision)):
        blockers.append(f"{prefix}:invalid_revision")
    content_hash = str(reference.get("content_hash") or "").strip()
    if content_hash and (len(content_hash) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in content_hash)):
        blockers.append(f"{prefix}:invalid_content_hash")
    ranges = reference.get("ranges", []) or []
    if not isinstance(ranges, (list, tuple)):
        blockers.append(f"{prefix}:invalid_ranges")
    else:
        for item in ranges:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                blockers.append(f"{prefix}:invalid_range")
                continue
            try:
                start, end = int(item[0]), int(item[1])
            except (TypeError, ValueError):
                blockers.append(f"{prefix}:invalid_range")
                continue
            if start <= 0 or end < start:
                blockers.append(f"{prefix}:invalid_range")
    return blockers


def _package_hash(payload: Mapping[str, Any]) -> str:
    identity = {
        "schema": payload.get("schema"),
        "task_id": payload.get("task_id"),
        "attempt_id": payload.get("attempt_id", ""),
        "planner_decision_id": payload.get("planner_decision_id", ""),
        "planner_plan_id": payload.get("planner_plan_id", ""),
        "context_policy": payload.get("context_policy"),
        "selected_capability_ids": list(payload.get("selected_capability_ids", []) or []),
        "materialized_context_ids": list(payload.get("materialized_context_ids", []) or []),
        "serialized_context_ids": list(payload.get("serialized_context_ids", []) or []),
        "source_mode": payload.get("source_mode", "NO_SOURCE"),
        "source_references": list(payload.get("source_references", []) or []),
        "consumer_role": payload.get("consumer_role", ""),
        "consumer_channel": payload.get("consumer_channel", ""),
        "worker_binding": dict(payload.get("worker_binding", {}) or {}),
        "receipt": dict(payload.get("receipt", {}) or {}),
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
