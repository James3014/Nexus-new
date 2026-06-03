from typing import List, Dict, Any
from nexus.feedback.contracts import VerifierSignal, FailurePattern, FeedbackDirective
from nexus.verifiers.contracts import VerifierVerdict

class FeedbackRouter:
    """
    🚏 Task T2: Feedback Router
    職責: 只負責「訊號映射 (Signal Mapping)」，將 Verifier Verdicts 轉化為 Patterns。
    """
    @staticmethod
    def map_verdicts(verdicts: List[VerifierVerdict]) -> FeedbackDirective:
        patterns = []
        hints = []
        
        for v in verdicts:
            if not v.passed:
                tags_str = str(v.failure_tags)
                if "MISSING:" in tags_str:
                    patterns.append(FailurePattern("IMPORT_ERROR", f"Missing symbols: {tags_str}", 0.8))
                    hints.append("IMPORT_AWARE_FIX")
                
                if "INHERITANCE" in v.verifier_name.upper():
                    patterns.append(FailurePattern("MRO_VIOLATION", "Broken class hierarchy", 0.9))
                    hints.append("HIERARCHY_PRESERVING")
                    
        return FeedbackDirective(
            identified_patterns=patterns,
            retry_hints=list(set(hints)),
            is_actionable=len(patterns) > 0
        )
