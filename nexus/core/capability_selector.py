from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexus.core.belief_contracts import CapabilityExecutionPlan, SkillSlot
from nexus.core.capability_constraints import CapabilityConstraints
from nexus.core.capability_registry import CapabilityRegistry
from nexus.core.capability_signal_set import CapabilitySignalSet

logger = logging.getLogger(__name__)


class CapabilitySelector:
    """🧠 The single source of truth decision engine that dynamically generates execution plans."""

    def __init__(
        self, registry: Optional[CapabilityRegistry] = None, project_root: Optional[str] = None
    ) -> None:
        self.registry = registry or CapabilityRegistry()
        self.project_root = project_root

    def _codeintel_query(self, signal_set: CapabilitySignalSet) -> Dict[str, Any]:
        try:
            root = Path(self.project_root) if self.project_root else Path.cwd()
            src_dirs = [
                d
                for d in root.iterdir()
                if d.is_dir()
                and not d.name.startswith(("."))
                and d.name not in ("node_modules", ".git", "__pycache__")
            ]
            files = []
            for d in src_dirs[:5]:
                files.extend(list(d.rglob("*.py"))[:20])
            return {
                "status": "PASS",
                "files_scanned": min(len(files), 100),
                "directories_scanned": len(src_dirs),
                "impact_complexity": signal_set.impact_complexity,
            }
        except Exception as exc:
            return {"status": "FAIL", "reason": str(exc)}

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
            required_caps = [
                "mempalace",
                "autonomic_router",
                "belief",
                "repair_loop",
                "learning_closure",
            ]
            phases = [
                p
                for p in ["S", "P", "X", "D", "R", "A", "C"]
                if p not in lite_decision.skipped_phases
            ]
        else:
            phases = ["S", "P", "X", "D", "R", "A", "C"]
            query_lower = signal_set.task_desc.lower()

            # S (Scope)
            required_caps.append("mempalace")
            required_caps.append("zero_trust_v2_behavior")
            required_caps.append("nightshift_runner_service")
            if signal_set.risk_level in ("HIGH", "CRITICAL"):
                required_caps.append("policy_capability_gate")
                required_caps.append("entropy_guard_v2")

            # P (Plan)
            required_caps.append("autonomic_router")
            if signal_set.impact_complexity > 3.0:
                required_caps.append("predictive_auditor")
            if signal_set.risk_level in ("HIGH", "CRITICAL"):
                required_caps.append("spec_guarded")
            if "formula" in query_lower or "rule" in query_lower:
                required_caps.append("decision_formula_engine")

            # X (Recon)
            required_caps.append("codeintel")
            required_caps.append("lancedb")
            if "research" in query_lower or "source" in query_lower or "citation" in query_lower:
                required_caps.append("research")
                required_caps.append("research_and_source_discipline")
            if signal_set.belief_confidence < 0.5:
                required_caps.append("aos_oracle")
            if "refresh" in query_lower or "schedule" in query_lower:
                required_caps.append("learn_refresh_service")
                required_caps.append("learn_scheduler_service")
            if signal_set.belief_confidence > 0.8 and "optimize" in query_lower:
                required_caps.append("reflex_loop")

            # D (Decide)
            required_caps.append("belief")
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
            if (
                "battle" in query_lower
                or "campaign" in query_lower
                or signal_set.impact_complexity > 4.5
            ):
                required_caps.append("battle_swarm")
            if signal_set.risk_level == "CRITICAL":
                required_caps.append("sandbox_runner")
            required_caps.append("dual_loop")

            # A (Audit)
            required_caps.append("artifact_gate")
            required_caps.append("claim_gate")
            if signal_set.risk_level == "CRITICAL" or signal_set.impact_complexity > 4.0:
                required_caps.append("ultra_review")

            # C (Closure)
            required_caps.append("learning_closure")
            required_caps.append("metabolism_resume")
            required_caps.append("mfp_gate")
            required_caps.append("promotion_engine")
            required_caps.append("subagent_outcome_service")
            required_caps.append("attempt_settlement_service")

        # 2.7: M4 — CodeIntel/JIT 獨立查詢 (X/Recon 階段)
        if getattr(signal_set, "codeintel_query_available", False):
            try:
                evidence = self._codeintel_query(signal_set)
                signal_set.codeintel_evidence.update(evidence)
            except Exception as e:
                logger.debug("[CapabilitySelector] codeintel query failed: %s", e)

        # 3. 過濾與過濾黑名單規則 (Filter Out Blocked capabilities)
        # + NEXUS_SKIP_* env flag 支援 (N16-N22 M2 驗證用)
        final_caps: List[str] = []
        for cap_name in required_caps:
            info = self.registry.get_capability(cap_name)
            if not info:
                continue
            # NEXUS_SKIP_{CAP_NAME}=1 跳過 (M2 關閉測試)
            skip_env = f"NEXUS_SKIP_{cap_name.upper()}"
            if os.environ.get(skip_env) == "1":
                logger.debug("[Selector] Cap %s skipped via %s=1", cap_name, skip_env)
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
            if (
                "Mode C" in info.allowed_heep_modes
                and (
                    signal_set.risk_level in ("HIGH", "CRITICAL")
                    or signal_set.impact_complexity > 3.5
                )
                and not lite_decision.is_lite
            ):
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
