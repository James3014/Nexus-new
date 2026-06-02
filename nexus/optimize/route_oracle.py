from typing import Dict, Any

from nexus.optimize.contracts import RouteDecision

class RouteOracle:
    """
    ⚖️ Nexus Route Oracle (v2.5)
    """
    @staticmethod
    def decide_route(context: Dict[str, Any]) -> RouteDecision:
        risk_score = context.get("risk_score", 100)
        bare_sufficiency = context.get("bare_sufficiency", "low")

        if risk_score < 30:
            return RouteDecision(flow="baseline", lite_preferred=True, reason="low_risk_auto")
        
        if 30 <= risk_score <= 60 and bare_sufficiency == "high":
            return RouteDecision(flow="lite_supervised", lite_preferred=True, reason="medium_risk_bounded")
            
        return RouteDecision(flow="hyper_sprint", lite_preferred=False, reason="high_risk_or_uncertain")
