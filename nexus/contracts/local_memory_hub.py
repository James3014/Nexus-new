from __future__ import annotations

from typing import Any, Mapping


LOCAL_MEMORY_HUB_SCHEMA = "nexus.local_memory_hub.v1"
MEMORY_LEARNING_LINEAGE_SCHEMA = "nexus.memory_learning_lineage.v1"


def build_local_memory_hub_snapshot(
    *,
    capabilities: list[str] | tuple[str, ...],
    evidence_root: str,
    budget: Mapping[str, Any] | None = None,
    recent_receipts: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    blockers: list[str] = []
    clean_receipts = [
        receipt
        for receipt in recent_receipts
        if str(receipt.get("status") or "").upper() in {"PASS", "NOT_APPLICABLE"}
    ]
    if not evidence_root.strip():
        blockers.append("missing_evidence_root")
    if len(clean_receipts) != len(recent_receipts):
        blockers.append("recent_receipt_not_clean")
    capability_list = sorted({str(item).strip() for item in capabilities if str(item).strip()})
    if not capability_list:
        blockers.append("missing_capabilities")
    return {
        "schema": LOCAL_MEMORY_HUB_SCHEMA,
        "status": "PASS" if not blockers else "RETURN",
        "capabilities": capability_list,
        "health": "HEALTHY" if not blockers else "DEGRADED",
        "budget": dict(budget or {}),
        "evidence_root": evidence_root,
        "recent_receipt_count": len(recent_receipts),
        "clean_receipt_count": len(clean_receipts),
        "mutable_global_singleton": False,
        "distributed_heartbeat_required": False,
        "blockers": sorted(set(blockers)),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def build_memory_learning_lineage(
    *,
    task_id: str,
    attempt_id: str,
    action_id: str,
    retrieved_lesson_ids: list[str] | tuple[str, ...] = (),
    applied_lesson_ids: list[str] | tuple[str, ...] = (),
    lesson_disposition: str = "shadow",
    stable_knowledge_overwrite: bool = False,
    auto_replay_allowed: bool = False,
) -> dict[str, Any]:
    if stable_knowledge_overwrite:
        raise ValueError("MEMORY_LEARNING_STABLE_KNOWLEDGE_OVERWRITE_FORBIDDEN")
    if auto_replay_allowed:
        raise ValueError("MEMORY_LEARNING_AUTO_REPLAY_FORBIDDEN")
    return {
        "schema": MEMORY_LEARNING_LINEAGE_SCHEMA,
        "task_id": str(task_id),
        "attempt_id": str(attempt_id),
        "action_id": str(action_id),
        "retrieved_lesson_ids": sorted({str(item) for item in retrieved_lesson_ids}),
        "applied_lesson_ids": sorted({str(item) for item in applied_lesson_ids}),
        "lesson_disposition": str(lesson_disposition or "shadow"),
        "stable_knowledge_overwrite": False,
        "auto_replay_allowed": False,
    }
