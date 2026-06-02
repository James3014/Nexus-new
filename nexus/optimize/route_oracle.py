from typing import Dict, Any

class RouteOracle:
    """
    ⚖️ Task 1: RouteOracle
    職責: 單一 Admission 出口。依據風險分數與證據充足度決定推薦路徑。
    """
    @staticmethod
    def decide_route(context: Dict[str, Any]) -> Dict[str, Any]:
        risk_score = context.get("risk_score", 100)
        bare_sufficiency = context.get("bare_sufficiency", "low")

        # risk=low 必走 lite
        if risk_score < 30:
            return {"flow": "baseline", "lite_preferred": True, "reason": "low_risk_auto"}
        
        # risk 30-60 不得直接 full hypersprint
        if 30 <= risk_score <= 60 and bare_sufficiency == "high":
            return {"flow": "lite_supervised", "lite_preferred": True, "reason": "medium_risk_bounded"}
            
        return {"flow": "hyper_sprint", "lite_preferred": False, "reason": "high_risk_or_uncertain"}
