from typing import Optional, Dict, Any
from nexus.replay.replay_artifact import ReplayArtifact
from nexus.telemetry.telemetry_models import TelemetryBundle
from nexus.gate.gate_judge import GateJudge, BlockerCodes

class ExperimentalArchitectureGate:
    """
    🔬 Task: Observation-only Experimental Gate (Shadow-only)
    職責: 
    1. 在完全隔離、shadow-only 的模式下觀測實驗性模型 (例如 1.5B/3B/7B 學生/推薦模型) 的決策表現。
    2. 確保其決策結果「絕不變更」權威 outcome（不會介入實際路由或改變 decide 的 allowed 狀態）。
    3. 採集 shadow metrics 用於 Serving Maturity 評估。
    """
    
    @staticmethod
    def shadow_decide(ticket_id: str, 
                      replay: Optional[ReplayArtifact] = None, 
                      telemetry: Optional[TelemetryBundle] = None,
                      evidence_seal: Optional[Dict[str, Any]] = None,
                      experimental_advisor_decision: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        
        # 1. 取得權威基準判決 (Main path baseline)
        baseline_result = GateJudge.decide(ticket_id, replay, telemetry, evidence_seal)
        
        # 2. 如果沒有傳入實驗決策，則僅作為代理，返回基準
        if not experimental_advisor_decision:
            return {
                "task_id": ticket_id,
                "allowed": baseline_result["allowed"],
                "score": baseline_result["score"],
                "blocker": baseline_result["blocker"],
                "shadow_observation_only": True,
                "trust_mismatch_detected": False
            }
            
        # 3. 提取實驗決策的預測
        exp_allowed = experimental_advisor_decision.get("allowed", False)
        
        # 4. 判定 trust mismatch
        trust_mismatch = (exp_allowed != baseline_result["allowed"])
        
        return {
            "task_id": ticket_id,
            "allowed": baseline_result["allowed"], # ❗ 核心：絕對維持 baseline 決策，不得被實驗決策修改
            "score": baseline_result["score"],
            "blocker": baseline_result["blocker"],
            "shadow_observation_only": True,
            "experimental_advisor_decision": experimental_advisor_decision,
            "trust_mismatch_detected": trust_mismatch
        }
