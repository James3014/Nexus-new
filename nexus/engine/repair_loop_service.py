from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class RepairLoopService:
    """Orchestrate R-phase attempt loop with attempt executor and settlement service."""

    def __init__(self, *, project_root: Path, repair_attempt: Any, attempt_settlement: Any):
        self.project_root = Path(project_root)
        self.repair_attempt = repair_attempt
        self.attempt_settlement = attempt_settlement

    def run(
        self,
        *,
        task_id: str,
        task_desc: str,
        skill_id: str,
        state: Any,
        verify_cmds: list[str],
        run_dir: Path,
        skip_pregate_for_isolated_workspace: bool,
        battle_swarm: Any = None,
        reflex_loop: Any = None,
        skill_registry: Any = None,
        wisdom_vault: Any = None,
        max_attempts: int = 3,
    ) -> bool:
        state.current_phase = "R"
        for attempt in range(1, max_attempts + 1):
            logger.info("🛠️ [R-Stage] Executing %s Flow (Attempt %d)", skill_id, attempt)
            attempt_result = self.repair_attempt.execute_attempt(
                task_id=task_id,
                task_desc=task_desc,
                state=state,
                attempt=attempt,
                verify_cmds=verify_cmds,
                run_dir=run_dir,
                skip_pregate_for_isolated_workspace=skip_pregate_for_isolated_workspace,
                battle_swarm=battle_swarm,
                reflex_loop=reflex_loop,
                skill_registry=skill_registry,
                wisdom_vault=wisdom_vault,
            )
            if attempt_result.get("status") == "abort":
                break
            passed = bool(attempt_result.get("passed", False))
            gate_results = list(attempt_result.get("gate_results") or [])

            decision = self.attempt_settlement.settle_attempt(
                task_id=task_id,
                skill_id=skill_id,
                state=state,
                passed=passed,
                gate_results=gate_results,
            )
            if decision == "success":
                return True
            if decision == "writeback_pending":
                return False

        logger.info("❌ [%s] Mission Aborted after depletion of retries.", skill_id)
        return False
