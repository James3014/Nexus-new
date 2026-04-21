from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable


logger = logging.getLogger(__name__)


class AttemptSettlementService:
    """Settle one repair attempt: evidence, crystallize, learning finalize, and transaction."""

    def __init__(
        self,
        *,
        project_root: Path,
        run_dir: Path,
        metrics_agg: Any,
        crystallize_fn: Callable[[dict[str, Any]], None],
        transaction_mgr: Any,
        learning_finalize_fn: Callable[..., dict[str, Any]],
        reflex_loop: Any = None,
    ):
        self.project_root = Path(project_root)
        self.run_dir = Path(run_dir)
        self.metrics_agg = metrics_agg
        self.crystallize_fn = crystallize_fn
        self.transaction_mgr = transaction_mgr
        self.learning_finalize_fn = learning_finalize_fn
        self.reflex_loop = reflex_loop

    def settle_attempt(
        self,
        *,
        task_id: str,
        skill_id: str,
        state: Any,
        passed: bool,
        gate_results: list[dict[str, Any]],
    ) -> str:
        self._write_auto_evidence(task_id=task_id, passed=passed, gate_results=gate_results)

        payload = self.metrics_agg.aggregate_crystallize_payload(
            task_id, skill_id, passed, gate_results, state.metadata
        )
        self.crystallize_fn(payload)

        self._run_reflex_loop()
        learning_finalize = self.learning_finalize_fn(
            self.project_root,
            state,
            success=bool(passed),
            source="engine.coordinator",
        )

        if passed and not learning_finalize.get("writeback_required"):
            logger.info("✅ [%s] Successful crystallization.", skill_id)
            self.transaction_mgr.commit_if_passed(task_id)
            return "success"
        if passed and learning_finalize.get("writeback_required"):
            logger.info("📝 [%s] Code complete but write-back still pending.", skill_id)
            state.metadata["delivery_status"] = "code_done_writeback_pending"
            self.transaction_mgr.audit_rollback(task_id)
            return "writeback_pending"

        logger.info("🔄 Audit Rejected for %s. Retrying...", skill_id)
        self.transaction_mgr.audit_rollback(task_id)
        return "retry"

    def _run_reflex_loop(self) -> None:
        try:
            if self.reflex_loop:
                changes = self.reflex_loop.run_cycle()
                if changes:
                    logger.info("🧬 [ReflexLoop] Tuned components: %s", list(changes.keys()))
        except Exception as e:
            logger.error("⚠️ [ReflexLoop] Background optimization failed: %s", e)

    def _write_auto_evidence(self, *, task_id: str, passed: bool, gate_results: list[dict[str, Any]]) -> Path:
        evidence_path = self.project_root / ".nexus" / "reports" / "hallucination_evidence.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        auto_evidence = {
            "_source": "system",
            "final_response": f"Task {task_id} pregate {'PASSED' if passed else 'FAILED'}",
            "evidence_bundle": {
                "code_artifacts": [str(self.run_dir)],
                "test_artifacts": [
                    {
                        "cmd": r.get("cmd", ""),
                        "exit_code": r.get("exit_code", -1),
                        "passed": r.get("passed", False),
                        "stdout_tail": r.get("stdout_tail", ""),
                        "stderr_tail": r.get("stderr_tail", ""),
                    }
                    for r in gate_results
                ],
                "command_artifacts": [
                    f"{r.get('cmd', '')} -> rc={r.get('exit_code', -1)}" for r in gate_results
                ],
                "aggregates": {
                    "success_rate": sum(1 for r in gate_results if r.get("passed")) / max(len(gate_results), 1),
                    "total_commands": len(gate_results),
                },
            },
        }
        evidence_path.write_text(json.dumps(auto_evidence, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("🛡️ [Evidence:Auto] Written to %s (agent-tamper-proof)", evidence_path)
        return evidence_path
