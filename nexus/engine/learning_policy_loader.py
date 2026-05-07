from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.contracts.learning_experience import load_promoted_learning_policy


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
            "enforce_penalties": False,
        }
    }
