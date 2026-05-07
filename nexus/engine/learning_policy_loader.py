from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.contracts.learning_experience import load_promoted_learning_policy

DEFAULT_PROMOTED_POLICY_PATH = Path(".nexus") / "policy" / "promoted_learning_policy.json"


def load_learning_policy_budget(path: Path) -> dict[str, Any]:
    policy = load_promoted_learning_policy(path)
    if policy.get("schema_version") != "nexus_promoted_learning_policy.v1":
        return {}
    promoted = [str(item) for item in policy.get("promoted_capabilities", []) or [] if str(item).strip()]
    penalized = [str(item) for item in policy.get("penalized_capabilities", []) or [] if str(item).strip()]
    if not promoted and not penalized:
        return {}
    return {
        "learning_policy": {
            "source_experiences": [str(item) for item in policy.get("source_experiences", []) or []],
            "promoted_capabilities": promoted,
            "penalized_capabilities": penalized,
            "enforce_penalties": bool(policy.get("enforce_penalties", False)),
            "penalty_candidates": [str(item) for item in policy.get("penalty_candidates", []) or []],
        }
    }


def merge_runtime_learning_policy(project_root: Path, budget: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(budget or {})
    if isinstance(merged.get("learning_policy"), dict):
        return merged
    runtime_budget = load_learning_policy_budget(project_root / DEFAULT_PROMOTED_POLICY_PATH)
    if not runtime_budget:
        return merged
    merged.update(runtime_budget)
    return merged
