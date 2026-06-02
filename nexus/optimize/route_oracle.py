from typing import Dict, Any

class RouteOracle:
    """
    ⚖️ Nexus Route Oracle (v2.5)
    職責: 純粹的決策邏輯。依據風險與信心，判定推薦流程。
    """
    @staticmethod
    def decide_route(risk_score: int, bare_sufficiency: str) -> Dict[str, Any]:
        # 1. 低風險分流
        if risk_score < 30:
            return {"flow": "baseline", "lite_preferred": True, "reason": "low_risk_auto_pass"}
        
        # 2. 中風險分流 (Admission Calibration)
        if 30 <= risk_score <= 60 and bare_sufficiency == "high":
            return {"flow": "lite_supervised", "lite_preferred": True, "reason": "bounded_medium_risk"}
            
        # 3. 高風險分流
        if risk_score > 60:
            return {"flow": "hyper_sprint", "lite_preferred": False, "reason": "high_risk_forced_hyper"}
            
        return {"flow": "baseline", "lite_preferred": False, "reason": "default_fallback"}
