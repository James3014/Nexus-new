from typing import Dict, Any

class RouteOracle:
    """
    ⚖️ Nexus Route Oracle (v2.5)
    職責: 純粹的決策邏輯。依據風險與信心，判定推薦流程。
    不負責裝配能力鏈。
    """
    @staticmethod
    def recommend_flow(risk_score: int, bare_sufficiency: str, task_type: str) -> Dict[str, Any]:
        # 核心優化: Risk 30-60 的中風險任務不再直跳 Hypersprint
        if risk_score < 30:
            return {"flow": "baseline", "lite": True, "reason": "low_risk_auto_pass"}
        
        if 30 <= risk_score <= 60 and bare_sufficiency == "high":
            # [Optimization] 降級至 lite-supervised 而非 full hyper
            return {"flow": "lite_supervised", "lite": True, "reason": "bounded_medium_risk"}
            
        if risk_score > 60:
            return {"flow": "hyper_sprint", "lite": False, "reason": "high_risk_forced_hyper"}
            
        return {"flow": "baseline", "lite": False, "reason": "default_fallback"}
