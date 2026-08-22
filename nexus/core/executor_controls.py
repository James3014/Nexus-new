from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from nexus.core.belief_contracts import CapabilityExecutionPlan, CapabilityReceipt, SkillReceipt
from nexus.core.capability_registry import CapabilityRegistry
from nexus.core.capability_executor_registry import get_executor


class ExecutorControls:
    """⚙️ The Execution Controller driving HEEP plans and compiling immutable Receipts."""

    def __init__(
        self,
        project_root: str,
        registry: Optional[CapabilityRegistry] = None,
        gate_evaluator: Optional[Any] = None,
    ) -> None:
        self.project_root = project_root
        self.registry = registry or CapabilityRegistry()
        self.gate_evaluator = gate_evaluator

    def execute_plan(self, plan: CapabilityExecutionPlan, task_desc: str = "") -> List[CapabilityReceipt]:
        """Drive the CapabilityExecutionPlan phases, executing HEEP slots and return receipts."""
        receipts: List[CapabilityReceipt] = []

        logger.info("⚙️ [ExecutorControls] Starting execution plan: %s", plan.plan_id)

        from concurrent.futures import ThreadPoolExecutor

        # 依據 S,P,X,D,R,A,C 順序分階段執行 capabilities
        for phase in plan.phases:
            # 找出屬於當前 phase 的 capabilities
            phase_caps = []
            for cap_name in plan.required_capabilities:
                info = self.registry.get_capability(cap_name)
                if info and phase in info.phases:
                    phase_caps.append(cap_name)

            if not phase_caps:
                continue

            with ThreadPoolExecutor(max_workers=max(1, len(phase_caps))) as executor:
                def execute_single_cap(cap_name: str) -> CapabilityReceipt:
                    logger.info(
                        "⚙️ [ExecutorControls] [%s] Executing Capability: %s", phase, cap_name
                    )
                    cap_start = time.monotonic()

                    slots = plan.skill_slots.get(cap_name) or []
                    skill_receipts: List[SkillReceipt] = []

                    # A planned SkillSlot proves selection only. Do not fabricate physical use.
                    for slot in slots:
                        logger.debug(
                            "⚙️ [ExecutorControls]   -> Selecting HEEP Role Slot: %s [%s]",
                            slot.skill_id,
                            slot.role,
                        )
                        selected_evidence_id = f"ev_slot_selected_{slot.skill_id}_{os.urandom(4).hex()}"
                        receipt = SkillReceipt(
                            skill_id=slot.skill_id,
                            selected=True,
                            used=False,
                            evidence_id=selected_evidence_id,
                            outcome={
                                "role_selected": slot.role,
                                "execution_state": "NOT_EXECUTED",
                                "reason": "skill_use_not_evidenced",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            },
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        )
                        skill_receipts.append(receipt)

                    def non_execution_receipt(reason: str) -> CapabilityReceipt:
                        elapsed_ms = max(0, int((time.monotonic() - cap_start) * 1000))
                        outcome = {
                            "phase_executed": phase,
                            "execution_state": "NOT_EXECUTED",
                            "error": reason,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        return CapabilityReceipt(
                            capability_name=cap_name,
                            selected=True,
                            invoked=False,
                            evidence_id=f"ev_cap_{cap_name}_not_invoked_{os.urandom(4).hex()}",
                            gate_passed=False,
                            outcome=outcome,
                            skill_receipts=skill_receipts,
                            telemetries={
                                "wall_time_ms": None,
                                "overhead_ms": None,
                                "token_usage": None,
                                "provider_costs": None,
                                "model_calls": 0,
                                "telemetry_source": "unavailable",
                                "claimable": False,
                                "missing_evidence_reason": reason,
                                "controller_wall_time_ms": elapsed_ms,
                            },
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        )

                    # Gate capabilities retain the structural compatibility evaluation below.
                    _GATE_CAPS = frozenset({"artifact_gate", "claim_gate"})
                    if cap_name not in _GATE_CAPS:
                        executor_fn = get_executor(cap_name)
                        if executor_fn is None:
                            return non_execution_receipt("executor_missing")

                        try:
                            _constraints = dict(plan.constraints)
                            _constraints["project_root"] = self.project_root
                            _plan_with_ctx = CapabilityExecutionPlan(
                                plan_id=plan.plan_id, task_id=plan.task_id,
                                phases=plan.phases, required_capabilities=plan.required_capabilities,
                                skill_slots=plan.skill_slots, constraints=_constraints,
                                timestamp=plan.timestamp,
                            )
                            cap_receipt = executor_fn(_plan_with_ctx, task_desc)
                        except Exception as exc:
                            logger.warning(
                                "ExecutorControls: real executor for %s failed (%s)",
                                cap_name,
                                type(exc).__name__,
                            )
                            return non_execution_receipt("executor_exception")

                        # Preserve the real executor's invocation truth even when it is False.
                        elapsed_ms = max(0, int((time.monotonic() - cap_start) * 1000))
                        existing = dict(cap_receipt.telemetries or {})
                        if cap_receipt.invoked:
                            existing["wall_time_ms"] = elapsed_ms
                            existing["overhead_ms"] = elapsed_ms
                            existing["telemetry_source"] = "measured"
                        else:
                            # A controller call happened, but the capability did not physically execute.
                            existing["wall_time_ms"] = None
                            existing["overhead_ms"] = None
                            existing["telemetry_source"] = "unavailable"
                            existing["missing_evidence_reason"] = (
                                existing.get("missing_evidence_reason") or "capability_not_invoked"
                            )
                            existing["controller_wall_time_ms"] = elapsed_ms
                        existing["claimable"] = False

                        # Executor-produced receipts are authoritative for a matching skill_id.
                        # Keep selected-only placeholders only when the executor did not report
                        # that skill, preventing contradictory used=False/used=True states here.
                        executor_skill_receipts = list(cap_receipt.skill_receipts or [])
                        executor_skill_ids = {receipt.skill_id for receipt in executor_skill_receipts}
                        merged_skill_receipts = [
                            receipt
                            for receipt in skill_receipts
                            if receipt.skill_id not in executor_skill_ids
                        ] + executor_skill_receipts

                        return CapabilityReceipt(
                            capability_name=cap_receipt.capability_name,
                            selected=True,
                            invoked=bool(cap_receipt.invoked),
                            evidence_id=cap_receipt.evidence_id,
                            gate_passed=(
                                bool(cap_receipt.gate_passed) if cap_receipt.invoked else False
                            ),
                            outcome=dict(cap_receipt.outcome or {}),
                            skill_receipts=merged_skill_receipts,
                            telemetries=existing,
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        )

                    # Structural compatibility path for artifact_gate / claim_gate only.
                    gate_passed = True
                    if self.gate_evaluator is not None:
                        blockers = []
                        from pathlib import Path
                        wiki_audit = Path(self.project_root) / "wiki_audit.json"
                        reports_dir = Path(self.project_root) / ".nexus" / "reports"
                        has_evidence = wiki_audit.exists() or (
                            reports_dir.exists() and any(reports_dir.iterdir())
                        )
                        if not has_evidence:
                            blockers.append("MISSING_EVIDENCE_REPORTS")
                        from nexus.core.gate_rules_builtin import BlockerCleanRule
                        chain_res = self.gate_evaluator.evaluate_rule_chain(
                            [BlockerCleanRule()], {"blockers": blockers}
                        )
                        gate_passed = (chain_res.verdict == "GREEN")
                    else:
                        from pathlib import Path
                        wiki_audit = Path(self.project_root) / "wiki_audit.json"
                        reports_dir = Path(self.project_root) / ".nexus" / "reports"
                        has_evidence = wiki_audit.exists() or (
                            reports_dir.exists() and any(reports_dir.iterdir())
                        )
                        if not has_evidence:
                            gate_passed = False

                    elapsed_ms = max(0, int((time.monotonic() - cap_start) * 1000))
                    return CapabilityReceipt(
                        capability_name=cap_name,
                        selected=True,
                        invoked=True,
                        evidence_id=f"ev_cap_{cap_name}_{os.urandom(4).hex()}",
                        gate_passed=gate_passed,
                        outcome={
                            "phase_executed": phase,
                            "slot_count": len(slots),
                            "compatibility_gate_evaluated": True,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                        skill_receipts=skill_receipts,
                        telemetries={
                            "wall_time_ms": elapsed_ms,
                            "overhead_ms": elapsed_ms,
                            "token_usage": 0,
                            "provider_costs": 0.0,
                            "model_calls": 0,
                            "telemetry_source": "measured",
                            "claimable": False,
                        },
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )

                # 提交並收集並行執行結果
                results = executor.map(execute_single_cap, phase_caps)
                receipts.extend(results)

        logger.info(
            "⚙️ [ExecutorControls] Plan %s completed. receipts compiled: %d",
            plan.plan_id,
            len(receipts),
        )
        return receipts
