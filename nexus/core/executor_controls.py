from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from nexus.core.belief_contracts import CapabilityExecutionPlan, CapabilityReceipt, SkillReceipt
from nexus.core.capability_registry import CapabilityRegistry


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

    def execute_plan(self, plan: CapabilityExecutionPlan) -> List[CapabilityReceipt]:
        """Drive the CapabilityExecutionPlan phases, executing HEEP slots and return receipts."""
        receipts: List[CapabilityReceipt] = []

        logger.info("⚙️ [ExecutorControls] Starting execution plan: %s", plan.plan_id)

        from concurrent.futures import ThreadPoolExecutor

        # 依據 S,P,X,D,R,A,C 順序分階段執行 capabilities
        for phase in plan.phases:
            # 找出屬於當前 phase 的 capabilities
            phase_caps = []
            for cap_name in plan.required_capabilities:
                # 簡單依據 cap_name 取得 registry info
                info = self.registry.get_capability(cap_name)
                if info and phase in info.phases:
                    phase_caps.append(cap_name)

            if not phase_caps:
                continue

            # 使用 ThreadPoolExecutor 並行執行同一個 Phase 中的所有 capabilities
            with ThreadPoolExecutor(max_workers=max(1, len(phase_caps))) as executor:
                def execute_single_cap(cap_name: str) -> CapabilityReceipt:
                    logger.info(
                        "⚙️ [ExecutorControls] [%s] Executing Capability: %s", phase, cap_name
                    )

                    # 1. 取得該能力下被裝配的 SkillSlots
                    slots = plan.skill_slots.get(cap_name) or []
                    skill_receipts: List[SkillReceipt] = []

                    # 2. 驅動執行每一個 SkillSlot 技能 (P9 & P11 實作)
                    for slot in slots:
                        logger.debug(
                            "⚙️ [ExecutorControls]   -> Injecting HEEP Role Slot: %s [%s]",
                            slot.skill_id,
                            slot.role,
                        )

                        # 模擬執行並累積 Evidence
                        mock_evidence_id = f"ev_slot_{slot.skill_id}_{os.urandom(4).hex()}"
                        outcome = {
                            "role_injected": slot.role,
                            "execution_state": "SUCCESS",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }

                        # 產生 SkillReceipt
                        receipt = SkillReceipt(
                            skill_id=slot.skill_id,
                            selected=True,
                            used=True,
                            evidence_id=mock_evidence_id,
                            outcome=outcome,
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        )
                        skill_receipts.append(receipt)

                    # 3. 執行能力品質 Gate 審計 (Audit phase - P15 實體對位)
                    gate_passed = True
                    if self.gate_evaluator is not None:
                        blockers = []
                        if cap_name in ("artifact_gate", "claim_gate"):
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
                        if cap_name in ("artifact_gate", "claim_gate"):
                            from pathlib import Path

                            wiki_audit = Path(self.project_root) / "wiki_audit.json"
                            reports_dir = Path(self.project_root) / ".nexus" / "reports"
                            # 確認確實有產出 evidence/artifact 報表
                            has_evidence = wiki_audit.exists() or (
                                reports_dir.exists() and any(reports_dir.iterdir())
                            )
                            if not has_evidence:
                                gate_passed = False

                    mock_cap_evidence_id = f"ev_cap_{cap_name}_{os.urandom(4).hex()}"

                    # 4. 產生 CapabilityReceipt (P10 實作)
                    return CapabilityReceipt(
                        capability_name=cap_name,
                        selected=True,
                        invoked=True,
                        evidence_id=mock_cap_evidence_id,
                        gate_passed=gate_passed,
                        outcome={
                            "phase_executed": phase,
                            "slot_count": len(slots),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                        skill_receipts=skill_receipts,
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
