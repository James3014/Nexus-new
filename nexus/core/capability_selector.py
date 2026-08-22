from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexus.core.belief_contracts import CapabilityExecutionPlan, SkillSlot
from nexus.core.capability_constraints import CapabilityConstraints
from nexus.core.capability_registry import CapabilityRegistry
from nexus.core.capability_signal_set import CapabilitySignalSet

logger = logging.getLogger(__name__)


class CapabilitySelector:
    """Legacy compatibility projection of CapabilityPlanner-owned decisions.

    This class intentionally retains the historical ``CapabilityExecutionPlan``
    shape for callers that have not migrated yet.  It is not a route or
    capability-selection authority: the selected set and execution depth come
    from ``CapabilityPlanner`` and this facade only projects capabilities that
    have an explicit canonical/legacy identity relationship.
    """

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

        from nexus.engine.capability_planner import CapabilityPlanner
        from nexus.services.mainchain_route_freeze import resolve_alias

        risk_score = {
            "LOW": 10,
            "NORMAL": 30,
            "HIGH": 70,
            "CRITICAL": 95,
        }.get(signal_set.risk_level, 30)
        route_features = {
            "risk_score": risk_score,
            "impact_complexity": signal_set.impact_complexity,
            "adjusted_root_cause_confidence": signal_set.belief_confidence,
            "candidate_count": int(signal_set.metadata.get("candidate_count") or 1),
            "is_cross_module_task": bool(signal_set.metadata.get("is_cross_module_task", False)),
            "has_hard_signal": bool(signal_set.metadata.get("has_hard_signal", False)),
        }
        planner_route = {
            "recommended_flow": str(signal_set.metadata.get("recommended_flow") or ""),
            "route_features": route_features,
            "prompt_compression": bool(signal_set.metadata.get("prompt_compression", False)),
            "local_enabled": bool(signal_set.metadata.get("local_enabled", False)),
        }
        planner_plan = CapabilityPlanner().plan(
            task_desc=signal_set.task_desc,
            task_type=str(signal_set.metadata.get("task_type") or "legacy_compat"),
            route=planner_route,
            codeintel=dict(signal_set.codeintel_evidence or {}),
            skills=[{"skill_id": skill_id} for skill_id in signal_set.skills_triggered],
        )
        if planner_plan.signal_snapshot.get("route_truth_source") != "CapabilityPlanner":
            raise ValueError("legacy_projection_requires_capability_planner_truth")

        canonical_selected = set(planner_plan.selected_capabilities)
        required_caps = []
        for info in self.registry.list_all_capabilities():
            legacy_name = str(info.name)
            if resolve_alias(legacy_name) in canonical_selected:
                required_caps.append(legacy_name)

        phases = (
            ["S", "P", "R", "C"]
            if planner_plan.execution_depth == "LIGHT"
            else ["S", "P", "X", "D", "R", "A", "C"]
        )
        forbidden_rules = verdict.get("forbidden_skills_rules", [])

        # 2.7: M4 — CodeIntel/JIT 獨立查詢 (X/Recon 階段)
        if getattr(signal_set, "codeintel_query_available", False):
            try:
                evidence = self._codeintel_query(signal_set)
                signal_set.codeintel_evidence.update(evidence)
            except Exception as e:
                logger.debug("[CapabilitySelector] codeintel query failed: %s", e)

        # 3. Compatibility projection only.  Legacy skip/forbid controls may
        # block the whole request through CapabilityConstraints above, but they
        # may not mutate CapabilityPlanner's selected set after planning.
        final_caps: List[str] = list(dict.fromkeys(required_caps))

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
                and planner_plan.execution_depth != "LIGHT"
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
                "selection_authority": "CapabilityPlanner",
                "canonical_selected_capabilities": list(planner_plan.selected_capabilities),
                "execution_depth": planner_plan.execution_depth,
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
