from __future__ import annotations

from typing import Any

# LANE_POLICY_DEFAULTS defines lane-level default route cost controls.
# Centralized in nexus/core to serve as a single source of truth for both engine and scripts.
LANE_POLICY_DEFAULTS: dict[str, dict[str, Any]] = {
    "hidden_bugfix_supervised": {
        "allow_pre_model_deterministic_rescue": True,
    },
    "governance_hardened": {
        "skip_llm_baseline": True,
    },
    "governance_hardened_capped": {
        "skip_llm_baseline": True,
    },
    "context_sync_capped": {
        "supervised_bare_first": True,
    },
}
