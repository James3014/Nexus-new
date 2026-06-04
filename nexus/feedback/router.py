from typing import List, Dict, Any
from nexus.feedback.contracts import VerifierSignal, FailurePattern, FeedbackDirective
from nexus.verifiers.contracts import VerifierVerdict

class FeedbackRouter:
    """
    🚏 Task T4: Feedback Router (Mapper)
    職責: 純粹的「翻譯官」。將 Verifier Verdicts 轉化為中立的 Failure Patterns。
    """
    @staticmethod
    def map_verdicts(verdicts: List[VerifierVerdict]) -> List[FailurePattern]:
        patterns = []
        
        for v in verdicts:
            if not v.passed:
                tags_str = str(v.failure_tags)
                if "MISSING:" in tags_str:
                    patterns.append(FailurePattern(
                        pattern_code="IMPORT_ERROR",
                        description=f"Missing: {tags_str}",
                        severity=0.8
                    ))
                
                if "INHERITANCE" in v.verifier_name.upper():
                    patterns.append(FailurePattern(
                        pattern_code="MRO_VIOLATION",
                        description="Hierarchy Broken",
                        severity=0.9
                    ))
                    
        return patterns
