from __future__ import annotations

from typing import Any

# LANE_POLICY_DEFAULTS defines lane-level default route cost controls.
# According to rule: "feature rule 覆蓋 lane default 的顯式欄位，未聲明欄位才回退到 lane default"
# Feature rules override explicit fields of lane defaults, and undeclared fields fallback to lane defaults.
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
