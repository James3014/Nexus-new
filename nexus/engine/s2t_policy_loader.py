from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from nexus.engine.learning_policy_store import DEFAULT_LEARNING_POLICY_STORE, LearningPolicyStore


DEFAULT_S2T_POLICY_DRAFT_PATH = Path(".nexus") / "policy" / "promoted_s2t_policy_draft.json"


def load_s2t_policy_draft_budget(path: Path, store: LearningPolicyStore | None = None) -> dict[str, Any]:
    try:
        policy = (store or DEFAULT_LEARNING_POLICY_STORE).read_json_policy(path)
    except (OSError, ValueError):
        return {}
    if policy.get("schema") != "nexus_promoted_s2t_policy_draft_v1":
        return {}
    status = str(policy.get("status") or "")
    runtime_promotable = status == "PROMOTED_RUNTIME" and s2t_promotion_gate_passed(policy)
    if status != "DRAFT_SHADOW_ONLY" and not runtime_promotable:
        return {}
    task_rules = policy.get("task_rules", {})
    task_rules = task_rules if isinstance(task_rules, dict) else {}
    if not task_rules:
        return {}
    return {
        "s2t_policy_draft": {
            "schema": str(policy.get("schema") or ""),
            "status": status,
            "source_schema": str(policy.get("source_schema") or ""),
            "trace_event_schema": str(policy.get("trace_event_schema") or ""),
            "runtime_promotable": runtime_promotable,
            "promotion_gate": policy.get("promotion_gate", {}) if isinstance(policy.get("promotion_gate", {}), dict) else {},
            "task_rules": task_rules,
        }
    }


def merge_runtime_s2t_policy_draft(
    project_root: Path,
    budget: dict[str, Any] | None = None,
    store: LearningPolicyStore | None = None,
) -> dict[str, Any]:
    merged = dict(budget or {})
    if isinstance(merged.get("s2t_policy_draft"), dict):
        return merged
    if os.environ.get("NEXUS_DISABLE_S2T_POLICY_DRAFT", "").strip().lower() in {"1", "true", "yes"}:
        return merged
    runtime_budget = load_s2t_policy_draft_budget(project_root / DEFAULT_S2T_POLICY_DRAFT_PATH, store=store)
    if runtime_budget:
        merged.update(runtime_budget)
    return merged


def s2t_promotion_gate_passed(policy: dict[str, Any]) -> bool:
    gate = policy.get("promotion_gate", {})
    if not isinstance(gate, dict) or gate.get("passed") is not True:
        return False
    try:
        trust_mismatch_rate = float(gate.get("trust_mismatch_rate", 1.0))
        sample_count = int(gate.get("sample_count", 0))
    except (TypeError, ValueError):
        return False
    rollback_policy = str(gate.get("rollback_policy") or "").strip()
    return trust_mismatch_rate == 0.0 and sample_count >= 1 and bool(rollback_policy)
