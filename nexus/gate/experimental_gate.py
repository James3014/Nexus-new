import os
import json
import time
from typing import Optional, Dict, Any, List
from pathlib import Path
from nexus.replay.replay_artifact import ReplayArtifact
from nexus.telemetry.telemetry_models import TelemetryBundle
from nexus.gate.gate_judge import GateJudge, BlockerCodes

EVIDENCE_LOG_PATH = Path(".nexus/metrics/s2t_shadow_contract_evidence.jsonl")

class OptionalGatekeeper15B:
    """
    🔬 Phase 3: Optional 1.5B Gatekeeper
    職責:
    1. 前門篩選，分析 task_payload。
    2. 輸出 Gatekeeper V2 Schema hints: need_3b, need_deliberation, risk_tier, phase_hint, confidence_band, abstain_reason。
    3. 優化短任務 (short tasks) 的 E2E 延遲，防止高成本模型 (7B/14B) 的誤觸發。
    """
    
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def screen(self, task_payload: Dict[str, Any]) -> Dict[str, Any]:
        """前門篩選與 hint 輸出。"""
        if not self.enabled or os.getenv("NEXUS_GATEKEEPER_15B_ENABLED", "1") == "0":
            return {
                "need_3b": True,
                "need_deliberation": False,
                "risk_tier": "low",
                "phase_hint": "intake",
                "confidence_band": "high",
                "abstain_reason": None
            }

        task_type = str(task_payload.get("task_type", "")).lower()
        value_tier = float(task_payload.get("value_tier", 0.0))
        
        # 實作前門分類：短任務或普通 bugfix 僅分配 3B，無需 7B/14B deliberation
        if task_type in ["bugfix", "format", "doc"] and value_tier < 50.0:
            return {
                "need_3b": True,
                "need_deliberation": False,
                "risk_tier": "low",
                "phase_hint": "execution",
                "confidence_band": "high",
                "abstain_reason": None
            }
        
        # 高風險/高難度任務建議 7B/14B deliberation
        if task_type in ["research", "repair-review", "synthesis-review"] or value_tier >= 100.0:
            return {
                "need_3b": True,
                "need_deliberation": True,
                "risk_tier": "high",
                "phase_hint": "review",
                "confidence_band": "medium",
                "abstain_reason": None
            }

        return {
            "need_3b": True,
            "need_deliberation": False,
            "risk_tier": "medium",
            "phase_hint": "plan",
            "confidence_band": "high",
            "abstain_reason": None
        }


class ExperimentalArchitectureGate:
    """
    🔬 Task: Observation-only Experimental Gate (Shadow-only Contract)
    職責: 
    1. 在完全隔離、shadow-only 的模式下觀測實驗性模型 (例如 1.5B/3B/7B 推薦模型) 的決策表現。
    2. 確保其決策結果「絕不變更」權威 outcome（不會介入實際路由或改變 decide 的 allowed 狀態）。
    3. 實作平滑退避 (Smooth Fallback) 防禦：任何 shadow advisor 異常皆不影響主路徑。
    4. 採集 shadow metrics 與決策對比，記錄至追加式證據日誌。
    5. Phase 5 Maturity Checklist 檢核：未通過則鎖死為 shadow-first 模式。
    """
    
    @staticmethod
    def check_maturity(model_id: str, specs: Dict[str, Any]) -> bool:
        """
        Phase 5 Maturity Checklist 檢核。
        必須具備: rollback_path, token_budget, runtime_fitness_report。
        """
        required_keys = ["rollback_path", "token_budget", "runtime_fitness_report"]
        for key in required_keys:
            if key not in specs or not specs[key]:
                return False
        
        # Token budget constraint check (例如單次任務不可大於 1,000,000 tokens)
        if float(specs.get("token_budget", 0)) > 1000000.0:
            return False
            
        return True

    @staticmethod
    def shadow_decide(ticket_id: str, 
                      replay: Optional[ReplayArtifact] = None, 
                      telemetry: Optional[TelemetryBundle] = None,
                      evidence_seal: Optional[Dict[str, Any]] = None,
                      experimental_advisor_decision: Optional[Dict[str, Any]] = None,
                      model_id: str = "unknown",
                      model_specs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        
        # 1. 取得權威基準判決 (Main path baseline)
        baseline_result = GateJudge.decide(ticket_id, replay, telemetry, evidence_seal)
        
        # 2. 檢查 Feature Flag 控制
        shadow_enabled = os.environ.get("NEXUS_SHADOW_ADVISOR_ENABLED", "False").lower() in ("true", "1", "yes")
        
        if not shadow_enabled:
            return baseline_result

        fallback_triggered = False
        is_mismatch = False
        advisor_decision_used = None
        
        # 3. Phase 5 Maturity check: 檢核未過則強制 locked 於 shadow
        is_mature = False
        if model_specs:
            is_mature = ExperimentalArchitectureGate.check_maturity(model_id, model_specs)
            
        try:
            if experimental_advisor_decision:
                advisor_decision_used = experimental_advisor_decision
                exp_allowed = experimental_advisor_decision.get("allowed", False)
                is_mismatch = (exp_allowed != baseline_result["allowed"])
            else:
                fallback_triggered = True
        except Exception as e:
            fallback_triggered = True
            is_mismatch = False
            advisor_decision_used = {"error": str(e)}

        # 4. 追加寫入決策對比證據日誌 (Per-row Evidence Logging)
        try:
            EVIDENCE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            log_record = {
                "timestamp": time.time(),
                "ticket_id": ticket_id,
                "model_id": model_id,
                "baseline_decision": baseline_result,
                "advisor_decision": advisor_decision_used,
                "is_mismatch": is_mismatch,
                "fallback_triggered": fallback_triggered,
                "shadow_enabled": shadow_enabled,
                "is_mature": is_mature
            }
            with open(EVIDENCE_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_record, ensure_ascii=False) + "\n")
        except Exception as log_err:
            print(f"⚠️ Warning: Failed to write shadow contract evidence: {log_err}")

        # 5. 回傳結果 (絕對維持 baseline 決策，不得被實驗決策修改)
        return {
            "task_id": ticket_id,
            "allowed": baseline_result["allowed"], 
            "score": baseline_result["score"],
            "blocker": baseline_result["blocker"],
            "shadow_observation_only": True,
            "experimental_advisor_decision": advisor_decision_used,
            "trust_mismatch_detected": is_mismatch,
            "fallback_triggered": fallback_triggered,
            "is_mature_for_main_path": is_mature
        }
