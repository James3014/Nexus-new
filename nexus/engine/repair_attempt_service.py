from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Callable

from nexus.engine.cli_pregate import run_cli_pregate
from nexus.engine.target_env_context import TargetEnvContext
from nexus.learning.lewm_predictor import LeWMPredictor


logger = logging.getLogger(__name__)


class RepairAttemptService:
    """Execute one repair attempt branch (JEPA / battle swarm / pregate)."""

    def __init__(
        self,
        *,
        project_root: Path,
        run_cli_pregate_fn: Callable[..., tuple[bool, list[dict[str, Any]]]] = run_cli_pregate,
        subprocess_run: Callable[..., Any] = subprocess.run,
        lewm_cls: type[LeWMPredictor] = LeWMPredictor,
    ):
        self.project_root = Path(project_root)
        self.run_cli_pregate_fn = run_cli_pregate_fn
        self.subprocess_run = subprocess_run
        self.lewm_cls = lewm_cls

    def execute_attempt(
        self,
        *,
        task_id: str,
        task_desc: str,
        state: Any,
        attempt: int,
        verify_cmds: list[str],
        run_dir: Path,
        skip_pregate_for_isolated_workspace: bool,
        battle_swarm: Any = None,
        reflex_loop: Any = None,
        skill_registry: Any = None,
        wisdom_vault: Any = None,
        target_env: TargetEnvContext | None = None,
    ) -> dict[str, Any]:
        if state.metadata.get("sim_lewm"):
            lewm = self.lewm_cls()
            sim_res = lewm.simulate(state.metadata.get("task_description", ""), None)
            sim_status = sim_res.get("status")
            if sim_status == "REJECTED":
                logger.warning("🚫 [JEPA] Simulator Rejected (Cost: %s)", sim_res.get("cost"))
                state.metadata["lewm_sim_status"] = "REJECTED"
                state.metadata["lewm_rejected_cost"] = sim_res.get("cost")
                return {"status": "abort", "passed": False, "gate_results": []}
            if sim_status == "PASSED":
                state.metadata["lewm_sim_status"] = "PASSED"
                state.metadata["lewm_prediction_cost"] = sim_res.get("cost")
            else:
                logger.info("ℹ️ [JEPA] Simulator %s. Continuing standard flow.", sim_status)
                state.metadata["lewm_sim_status"] = sim_status

        git_exists = (self.project_root / ".git").exists()
        if attempt == 2 and battle_swarm is not None and git_exists:
            workers = 4
            if reflex_loop is not None and hasattr(reflex_loop, "config"):
                workers = int(reflex_loop.config.get("battle_workers", 4) or 4)
            battle_swarm.default_workers = workers
            logger.info("⚔️ [BattleSwarm] Triggering Layer 4 Parallel Repair with %d workers...", workers)

            def swarm_worker(_strategy, wt_path, _tid, _desc, _ctx):
                if target_env is not None:
                    wt_env = TargetEnvContext(
                        engine_root=target_env.engine_root,
                        target_repo_root=Path(wt_path),
                        target_venv=target_env.target_venv,
                        run_dir=target_env.run_dir
                    )
                    pregate_root = wt_env
                else:
                    pregate_root = wt_path
                wt_passed, wt_gates = self.run_cli_pregate_fn(project_root=pregate_root, commands=verify_cmds)
                score = (sum(1 for g in wt_gates if g["passed"]) / max(len(wt_gates), 1)) * 10.0
                return {"passed": wt_passed, "score": score}

            battle_result = battle_swarm.trigger_battle(
                task_id=task_id,
                desc=task_desc,
                context=state.metadata,
                execute_fn=swarm_worker,
            )
            try:
                if battle_result.get("status") == "winner_found":
                    winner = battle_result["winner"]
                    logger.info("🏆 [BattleSwarm] Winner Strategy %s applied.", winner["strategy"])
                    branches = battle_result.get("branches_to_clean", [])
                    winner_branch = next((b for b in branches if winner["strategy"] in b), None)
                    if winner_branch:
                        self.subprocess_run(
                            ["git", "merge", "--squash", winner_branch],
                            cwd=str(self.project_root),
                            capture_output=True,
                        )
                    if wisdom_vault is not None:
                        from nexus.research.findings_distiller import FindingsDistiller
                        from nexus.research.findings_memory import FindingsMemoryStore

                        distiller = FindingsDistiller(
                            FindingsMemoryStore(self.project_root),
                            skill_registry,
                            wisdom_vault,
                        )
                        distiller.distill_battle_results(battle_result, task_id)
                    return {
                        "status": "ok",
                        "passed": True,
                        "gate_results": [{"status": "PASSED_VIA_SWARM", "passed": True}],
                    }

                effective_project_root = target_env if target_env is not None else run_dir
                passed, gate_results = self.run_cli_pregate_fn(project_root=effective_project_root, commands=verify_cmds)
                return {"status": "ok", "passed": bool(passed), "gate_results": gate_results}
            finally:
                battle_swarm.cleanup(battle_result)

        if skip_pregate_for_isolated_workspace:
            return {
                "status": "ok",
                "passed": True,
                "gate_results": [
                    {
                        "cmd": "_NO_VERIFY_COMMANDS",
                        "exit_code": 0,
                        "passed": True,
                        "pregate_skip": True,
                        "reason": "isolated_workspace_without_git",
                    }
                ],
            }

        effective_project_root = target_env if target_env is not None else run_dir
        passed, gate_results = self.run_cli_pregate_fn(project_root=effective_project_root, commands=verify_cmds)
        return {"status": "ok", "passed": bool(passed), "gate_results": gate_results}
