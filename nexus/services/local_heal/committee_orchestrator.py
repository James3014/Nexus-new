from typing import Any, Callable, List, Dict
import os
import time
import logging
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.orchestrator import HealOrchestrator
from nexus.committee.controller import CommitteeControllerV263

logger = logging.getLogger(__name__)

class CommitteeOrchestrator(HealOrchestrator):
    """
    🤝 Nexus Committee Orchestrator (v26)
    實施 Verifier-backed Committee Search。
    在 Patch Synthesis 階段進行多樣本採樣與 Borda 選優。
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.k = int(os.getenv("NEXUS_COMMITTEE_K", "3"))

    def run(self, ctx: HealContext) -> HealContext:
        if os.getenv("NEXUS_USE_COMMITTEE", "0") != "1":
            return super().run(ctx)

        logger.info(f"--- [COMMITTEE MODE ACTIVE] k={self.k} ---")
        
        # Phase 1-3: Linear Execution
        for phase in [self.repro_phase, self.plan_phase, self.loc_phase]:
            res = phase.execute(ctx)
            if not res.success:
                ctx.op.failure_reason = res.error_reason
                return ctx

        # Phase 4: Committee Patch Search
        committee = CommitteeControllerV263(ctx.op.instance_id)
        committee.enabled = True # 強制啟用
        
        proposals = []
        for i in range(self.k):
            logger.info(f"  🐝 Sampling candidate {i+1}/{self.k}...")
            res = self.patch_phase.execute(ctx)
            if res.success:
                proposals.append({
                    "model": "14B" if i == 0 else "7B", # 混合模型比例
                    "attempt": i + 1,
                    "raw_label": "r:0,d:0,p:3,c:0", 
                    "artifacts": [ctx.op.final_patch]
                })
        
        if not proposals:
            ctx.op.failure_reason = "COMMITTEE_COVERAGE_FAILURE"
            return ctx
            
        # 執行委員會決議
        receipt = committee.process_proposals(proposals)
        
        if receipt.winner_id:
            # 找到最優解
            # 注意：winner_id 格式為 {task}-{model}-{attempt}-{hash}
            try:
                parts = receipt.winner_id.split('-')
                attempt_idx = int(parts[-2]) - 1
                ctx.op.final_patch = proposals[attempt_idx]["artifacts"][0]
                logger.info(f"  🏆 Winner Selected: {receipt.winner_id}")
            except Exception as e:
                logger.error(f"  ❌ Error parsing winner_id: {e}")
                ctx.op.failure_reason = "COMMITTEE_WINNER_PARSING_ERROR"
                return ctx
            
            # Phase 5: Final Verification
            verify_res = self.verify_phase.execute(ctx)
            if verify_res.success:
                ctx.op.solve_eligible = True
            else:
                ctx.op.failure_reason = f"VERIFIER_REJECTION:{verify_res.error_reason}"
        else:
            ctx.op.failure_reason = "COMMITTEE_SELECTION_FAILURE"
            
        return ctx
