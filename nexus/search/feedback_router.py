from typing import List, Dict, Any, Optional
from nexus.verifiers.contracts import VerifierVerdict

class FeedbackRouter:
    """
    🚏 Task T2: Feedback Router
    職責: 將驗證器的失敗模式 (Failure Patterns) 映射為具體的搜尋/重試指令。
    """
    @staticmethod
    def route_failure(verdicts: List[VerifierVerdict]) -> Dict[str, Any]:
        hints = []
        strategies = []
        
        for v in verdicts:
            if not v.passed:
                # 1. 偵測特定失敗模式
                if "MISSING:" in str(v.failure_tags) or "UNDEFINED" in str(v.failure_tags):
                    hints.append("IMPORT_AWARE_FIX")
                    strategies.append("include_common_imports")
                
                if "INHERITANCE" in v.verifier_name.upper():
                    hints.append("HIERARCHY_PRESERVING")
                    strategies.append("analyze_mro_first")
                    
        return {
            "retry_hints": list(set(hints)),
            "suggested_strategies": list(set(strategies)),
            "feedback_loop_active": len(hints) > 0
        }
