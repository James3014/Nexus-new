from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from nexus.engine.cli_pregate import _auto_detect_verify_commands
from nexus.engine.target_env_context import TargetEnvContext


logger = logging.getLogger(__name__)


class RepairSetupService:
    """Repair preflight setup: validator gate, swarm orchestration, and verify command resolution."""

    def __init__(
        self,
        *,
        project_root: Path,
        hardened_validator: Any,
        swarm_planner: Any,
        federation: Any,
        detect_verify_commands_fn: Callable[[Path], list[str]] = _auto_detect_verify_commands,
    ):
        self.project_root = Path(project_root)
        self.hardened_validator = hardened_validator
        self.swarm_planner = swarm_planner
        self.federation = federation
        self.detect_verify_commands_fn = detect_verify_commands_fn

    def prepare(self, *, state: Any, target_env: TargetEnvContext | None = None) -> dict[str, Any]:
        state.current_phase = "A"
        logger.info("[%s] [Phase A] Hardening audit (AST X-Ray Scan)...", state.task_id)
        generated_code = state.metadata.get("generated_code", "")
        val_result = self.hardened_validator.validate_code(generated_code)
        if not val_result["passed"]:
            logger.error("[%s] [Phase A] REJECTED: Security Risk Found!", state.task_id)
            state.metadata["lewm_sim_status"] = "REJECTED"
            return {"proceed": False, "reason": "validator_rejected", "verify_cmds": [], "skip_pregate": False}

        state.current_phase = "P"
        is_swarm = bool(state.metadata.get("swarm_mode", False))
        if is_swarm:
            logger.info("[Phase P] Swarm Mode ACTIVE. Orchestrating DAG...")
            state.metadata["task_graph_nodes"] = 3
            state.metadata["orchestration_pattern"] = "DAG_ORCHESTRATOR"
            desc = state.metadata.get("task_description", "Feature development")
            self.swarm_planner.add_task(f"{state.task_id}-p1", f"Analyze and Prepare {desc}")
            self.swarm_planner.add_task(
                f"{state.task_id}-p2",
                f"Implement core services for {desc}",
                deps=[f"{state.task_id}-p1"],
            )
            self.swarm_planner.add_task(
                f"{state.task_id}-p3",
                f"Final Integration of {desc}",
                deps=[f"{state.task_id}-p2"],
            )
            ready = self.swarm_planner.get_ready_tasks()
            logger.info("🛰️ [Phase P] Orchestrated %d nodes in Swarm Graph.", len(ready))
            v_path = self.swarm_planner.create_virtual_workspace(state.task_id)
            logger.info("🛰️ [Swarm] Virtual Workspace deployed at: %s", v_path)

        if self.federation.quorum_check():
            selected_node = self.federation.select_node()
            logger.info(
                "🛰️ [NSP:Sensing] Quorum PASS. Transition: ISOLATED -> DISPATCHED (Node: %s)",
                selected_node or "all",
            )
        else:
            logger.warning("🛑 [NSP:Sensing] Quorum FAIL. Transition: ISOLATED -> FALLBACK_LOCAL")

        verify_cmds = state.metadata.get("verify_commands")
        if not verify_cmds:
            if target_env is not None:
                from nexus.engine.cli_pregate import build_verify_commands
                verify_cmds = build_verify_commands(target_env)
                root_for_git = target_env.target_repo_root
            else:
                verify_cmds = self.detect_verify_commands_fn(self.project_root)
                root_for_git = self.project_root
        else:
            verify_cmds = list(verify_cmds)
            root_for_git = target_env.target_repo_root if target_env is not None else self.project_root

        skip_pregate = bool(not verify_cmds and not (root_for_git / ".git").exists())
        return {
            "proceed": True,
            "reason": "ok",
            "verify_cmds": verify_cmds,
            "skip_pregate": skip_pregate,
        }
