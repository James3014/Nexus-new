from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _load_dynamic_learning_policy_safe(project_root: Optional[str]) -> dict:
    """Fail-safe loader for .nexus/memory/dynamic_learning_policy.json.
    Returns {promoted_capabilities: [...], penalized_capabilities: [...]}
    or empty dict on any error.
    """
    if not project_root:
        return {}
    try:
        path = Path(project_root) / ".nexus" / "memory" / "dynamic_learning_policy.json"
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            policy = json.load(f)
        if policy.get("schema_version") != "nexus_dynamic_learning_policy.v1":
            return {}
        if policy.get("status") != "PASS":
            return {}
        return {
            "promoted_capabilities": [str(c) for c in policy.get("promoted_capabilities", []) or [] if str(c).strip()],
            "penalized_capabilities": [str(c) for c in policy.get("penalized_capabilities", []) or [] if str(c).strip()],
        }
    except Exception as exc:
        logger.debug("[CapabilitySelector] dynamic_learning_policy load skipped: %s", exc)
        return {}

from nexus.core.belief_contracts import CapabilityExecutionPlan, SkillSlot
from nexus.core.capability_registry import CapabilityRegistry
from nexus.core.capability_signal_set import CapabilitySignalSet
from nexus.core.capability_constraints import CapabilityConstraints


class CapabilitySelector:
    """🧠 The single source of truth decision engine that dynamically generates execution plans."""

    def __init__(self, registry: Optional[CapabilityRegistry] = None, project_root: Optional[str] = None) -> None:
        self.registry = registry or CapabilityRegistry()
        self.project_root = project_root

    def select_capabilities(
        self,
        signal_set: CapabilitySignalSet,
        constraints: CapabilityConstraints,
    ) -> CapabilityExecutionPlan | Dict[str, Any]:
        """Evaluate snapshot signals against constraints to produce a serialized ExecutionPlan."""
        # 1. 安全與倫理過濾 (Ethical Filter Check)
        verdict = constraints.evaluate_constraints(signal_set)
        if verdict.get("status") == "BLOCKED":
            return {
                "status": "BLOCKED",
                "reason": verdict.get("reason", "ETHICAL_CONSTRAINT_VIOLATION"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        from nexus.core.lite_route_oracle import should_use_lite_route
        lane_name = signal_set.metadata.get("lane") or signal_set.metadata.get("lane_name")
        lite_decision = should_use_lite_route(
            risk_level=signal_set.risk_level,
            impact_complexity=signal_set.impact_complexity,
            belief_confidence=signal_set.belief_confidence,
            lane_name=lane_name,
        )

        required_caps: List[str] = []
        forbidden_rules = verdict.get("forbidden_skills_rules", [])

        # 2. 智慧能力動態選擇演算法 (Autonomic Adaptive Selection)
        if lite_decision.is_lite:
            # 🚀 輕量路由模式下，只保留最核心的 S-P-R-C 骨幹能力，跳過重度沙盒與多重自癒模組
            required_caps = ["mempalace", "autonomic_router", "belief", "repair_loop", "learning_closure"]
            phases = [p for p in ["S", "P", "X", "D", "R", "A", "C"] if p not in lite_decision.skipped_phases]
        else:
            phases = ["S", "P", "X", "D", "R", "A", "C"]
            # S (Scope)
            required_caps.append("mempalace")
            if signal_set.risk_level in ("HIGH", "CRITICAL"):
                required_caps.append("policy_capability_gate")

            # P (Plan)
            required_caps.append("autonomic_router")

            # X (Recon)
            required_caps.append("codeintel")
            required_caps.append("lancedb")
            query_lower = signal_set.task_desc.lower()
            if "research" in query_lower or "source" in query_lower or "citation" in query_lower:
                required_caps.append("research")
                required_caps.append("research_and_source_discipline")

            # D (Decide)
            required_caps.append("belief")
            # 🧪 [Round 20] Belief Shift Adaptive Thresholding
            if signal_set.belief_confidence < 0.65 or signal_set.risk_level == "CRITICAL":
                required_caps.append("autoreason")

            # R (Repair)
            if signal_set.impact_complexity > 3.5 or signal_set.risk_level == "CRITICAL":
                required_caps.append("hyper_sprint")
                required_caps.append("swarm_multi_agent")
            else:
                required_caps.append("repair_loop")

            if "background" in query_lower or "jobs" in query_lower:
                required_caps.append("drone")
            if "long" in query_lower or "overnight" in query_lower:
                required_caps.append("nightshift")

            # A (Audit)
            required_caps.append("artifact_gate")
            required_caps.append("claim_gate")
            if signal_set.risk_level == "CRITICAL" or signal_set.impact_complexity > 4.0:
                required_caps.append("ultra_review")

            # C (Closure)
            required_caps.append("learning_closure")
            required_caps.append("metabolism_resume")

        # 2.5: 套用動態學習政策 (RC-1 Learning Closure)
        learning_policy = _load_dynamic_learning_policy_safe(self.project_root)
        if learning_policy:
            penalized = set(learning_policy.get("penalized_capabilities", []))
            required_caps = [c for c in required_caps if c not in penalized]
            promoted = learning_policy.get("promoted_capabilities", [])
            existing = set(required_caps)
            for cap in promoted:
                if cap not in existing and self.registry.get_capability(cap):
                    required_caps.append(cap)
                    logger.debug("[CapabilitySelector] learning_policy promoted: %s", cap)
            if penalized:
                logger.debug("[CapabilitySelector] learning_policy penalized (removed): %s", penalized & existing)

        # 3. 過濾與過濾黑名單規則 (Filter Out Blocked capabilities)
        final_caps: List[str] = []
        for cap_name in required_caps:
            info = self.registry.get_capability(cap_name)
            if not info:
                continue
            # 檢查是否違反宮殿黑名單規則
            is_forbidden = False
            for rule in forbidden_rules:
                if cap_name in str(rule).lower():
                    is_forbidden = True
                    break
            if is_forbidden:
                logger.warning("🛡️ [Selector] Cap %s skipped due to forbid rule", cap_name)
                continue
            final_caps.append(cap_name)

        # 4. 動態裝配 SkillSlots (P7 實作)
        skill_slots = {}
        for cap_name in final_caps:
            info = self.registry.get_capability(cap_name)
            if not info:
                continue
            slots = []
            # Mode C 且 risk 較高時裝配 Swarm 複數協作 Assembly
            if "Mode C" in info.allowed_heep_modes and (
                signal_set.risk_level in ("HIGH", "CRITICAL") or signal_set.impact_complexity > 3.5
            ) and not lite_decision.is_lite:
                slots.append(
                    SkillSlot(
                        role="SCOUT",
                        skill_id="sf-systematic-codeintel-first-principles-thinking-f95019ea",
                    )
                )
                slots.append(SkillSlot(role="LOGIC", skill_id=info.default_skill))
                slots.append(
                    SkillSlot(
                        role="AUDIT",
                        skill_id="sf-systematic-artifact_gate-differential-review-461fbd0c",
                    )
                )
            else:
                # Mode A 或 Mode B，只裝配單一 LOGIC 插槽
                slots.append(SkillSlot(role="LOGIC", skill_id=info.default_skill))
            skill_slots[cap_name] = slots

        # 5. 生成階段 DAG (S,P,X,D,R,A,C)

        plan_id = f"plan_{signal_set.task_id}_{int(datetime.now(timezone.utc).timestamp())}"

        return CapabilityExecutionPlan(
            plan_id=plan_id,
            task_id=signal_set.task_id,
            phases=phases,
            required_capabilities=final_caps,
            skill_slots=skill_slots,
            constraints={
                "risk_level": signal_set.risk_level,
                "belief_confidence": signal_set.belief_confidence,
                "impact_complexity": signal_set.impact_complexity,
                "forbidden_rules": forbidden_rules,
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

