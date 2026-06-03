import os
from typing import List, Optional, Dict, Any
from nexus.committee.registry import CandidateRegistry
from nexus.committee.adapter import ProposerAdapter
from nexus.verifiers.registry import VerifierRegistry
from nexus.verifiers.packs.registry import PackRegistry
from nexus.verifiers.contracts import VerifierVerdict
from nexus.selection.calibrator import ConfidenceCalibrator
from nexus.selection.decision_policy import DecisionPolicy
from nexus.committee.models import CommitteeReceipt

class CommitteeControllerV263:
    """
    🎮 [NEXUS v26.6] 多軌演進控制器
    職責: 協調 Search -> Verifier Packs -> Selection (Cali -> Decision) 全管線。
    """
    def __init__(self, task_id: str, domains: List[str] = None):
        self.enabled = os.getenv("NEXUS_USE_COMMITTEE", "0") == "1"
        self.packs_enabled = os.getenv("NEXUS_USE_PACKS", "0") == "1"
        self.task_id = task_id
        self.domains = domains or ["astropy"] # 預設嘗試
        
        self.registry = CandidateRegistry(task_id)
        self.adapter = ProposerAdapter()
        self.calibrator = ConfidenceCalibrator()
        self.decision_policy = DecisionPolicy()

    def process_proposals(self, raw_proposals: List[Dict[str, Any]]) -> CommitteeReceipt:
        if not self.enabled:
            p = raw_proposals[0]
            candidate = self.adapter.create_candidate(self.task_id, p['model'], p['attempt'], p['raw_label'], [])
            return CommitteeReceipt(self.task_id, 1, [candidate], [], candidate.candidate_id, 'feature_disabled_fallback')

        # 1. Ingress
        for p in raw_proposals:
            candidate = self.adapter.create_candidate(
                self.task_id, p["model"], p["attempt"], p["raw_label"], p.get("artifacts", [])
            )
            self.registry.register(candidate)
        
        candidates = self.registry.get_all()
        all_verdicts = []
        
        # 2. Verification (Plugin & Pack Based)
        # 獲取基礎驗證器
        verifiers = VerifierRegistry.get_all_verifiers()
        # 獲取領域外掛包 (若啟用)
        if self.packs_enabled:
            packs = PackRegistry.get_enabled_packs(self.domains)
            for pack in packs:
                print(f"📦 [Pack] Engaging {pack.name} for domain {self.domains}")
                # 此處模擬將 Pack 內的驗證器加入管線
                # 真實邏輯中 Pack 會直接被執行
                pass 

        for c in candidates:
            patch_content = c.artifact_refs[0] if c.artifact_refs else ''
            # 執行基礎驗證
            for v in verifiers:
                all_verdicts.append(v.evaluate(c.candidate_id, patch_content))
            
            # 執行 Pack 驗證 (若啟用)
            if self.packs_enabled:
                for pack in PackRegistry.get_enabled_packs(self.domains):
                    all_verdicts.extend(pack.evaluate_all(c.candidate_id, patch_content))
            
        # 3. Selection (Calibration & Decision)
        # 初始信心值 0.7
        calibrated_data = self.calibrator.calibrate(all_verdicts, 0.7)
        
        # 執行決策
        selection_res = self.decision_policy.evaluate_and_decide(
            calibrated_data, 
            calibrated_data["calibrated_confidence"]
        )
        
        return CommitteeReceipt(
            task_id=self.task_id,
            k=len(candidates),
            candidates=candidates,
            verdicts=all_verdicts,
            winner_id=selection_res.winner_id,
            failure_bucket=selection_res.failure_bucket,
            confidence=selection_res.confidence,
            verifier_gap=selection_res.gap,
            total_cost=len(candidates) * 0.05
        )
