from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class AutonomicRoutingService:
    """Coordinator-facing wrapper for autonomic route resolution and side effects."""

    def __init__(
        self,
        *,
        project_root: Path,
        memory_service: Any = None,
        context_hub: Any = None,
        mem_palace: Any = None,
        selector: Any = None,
    ):
        self.project_root = Path(project_root)
        self.memory_service = memory_service
        self.context_hub = context_hub
        self.mem_palace = mem_palace
        self.selector = selector

    def apply(
        self,
        *,
        state: Any,
        task_id: str,
        task_desc: str,
        task_type: str,
        forecast: dict[str, Any],
    ) -> dict[str, Any]:
        direct_mode = bool(state.metadata.get("direct_mode"))
        if direct_mode:
            state.metadata["autonomic_route"] = "direct_mode"
            state.metadata["autonomic_reason"] = str(
                state.metadata.get("direct_mode_reason", "explicit_user_repair_spec")
            )
            state.metadata["est_tokens"] = forecast.get("est_tokens", 0)
            logger.info("⚡ [Autonomic] Direct Mode active: skip autonomic router/context injection.")
            return {
                "mode": state.metadata["autonomic_route"],
                "reason": state.metadata["autonomic_reason"],
            }

        from nexus.engine.autonomic_router import AutonomicRouter

        arouter = AutonomicRouter(
            project_root=str(self.project_root),
            memory_service=self.memory_service,
            mem_palace=self.mem_palace,
        )
        pre_routing = (
            self.context_hub.make_pre_routing_decision(task_id, state.metadata)
            if self.context_hub
            else {}
        )
        exec_plan = arouter.route(task_desc, state, forecast, pre_routing=pre_routing)

        state.metadata["autonomic_route"] = exec_plan.mode
        state.metadata["autonomic_reason"] = exec_plan.reason
        state.metadata["est_tokens"] = forecast.get("est_tokens", 0)

        if exec_plan.mode == "swarm":
            state.metadata["swarm_mode"] = True
            logger.info("🧠 [Autonomic] Auto-escalated to SWARM: %s", exec_plan.reason)
        elif exec_plan.mode == "research_first":
            state.metadata["force_external"] = True
            logger.info("🧠 [Autonomic] Auto-routed to RESEARCH_FIRST: %s", exec_plan.reason)
        elif exec_plan.mode == "self_heal" and self.selector:
            logger.info("🧠 [Autonomic] Priority: SELF_HEAL triggered by memory match.")
        elif exec_plan.mode == "external_skill":
            self._apply_external_skill(state=state, skill_id=str(getattr(exec_plan, "skill_id", "")))

        return {
            "mode": exec_plan.mode,
            "reason": exec_plan.reason,
            "skill_id": str(getattr(exec_plan, "skill_id", "")),
        }

    def _apply_external_skill(self, *, state: Any, skill_id: str) -> None:
        logger.info("🧠 [Autonomic] Priority: EXTERNAL_SKILL triggered. Binding %s...", skill_id)
        try:
            from nexus.core.unified_registry import UnifiedRegistry

            reg = UnifiedRegistry(self.project_root)
            reg.refresh()
            skill_data = reg.registry.get_by_task_id(skill_id)
            if skill_data and skill_data.get("external_path"):
                skill_md = Path(skill_data["external_path"]).read_text(
                    encoding="utf-8",
                    errors="replace",
                )
                state.metadata["active_external_skill"] = skill_data["name"]
                state.metadata["task_description"] += (
                    f"\n\n[EXTERNAL SKILL INSTRUCTIONS: {skill_data['name']}]\n{skill_md}"
                )
                logger.info("✅ [SkillEmbody] Injected %d bytes of tactical knowledge.", len(skill_md))
        except Exception as e:
            logger.warning("⚠️ [SkillEmbody] Failed to inject external skill: %s", e)
