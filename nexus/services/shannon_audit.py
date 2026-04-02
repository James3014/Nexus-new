from typing import Any, Dict, List, Optional, Tuple
import math
import logging

logger = logging.getLogger(__name__)

class ShannonAudit:
    """⚖️ [Wave 1] Shannon Entropy Audit: Detecting key leaks"""
    
    def __init__(self, threshold: float = 4.5):
        self.threshold = threshold

    def audit(self, text: str) -> Dict[str, Any]:
        entropy = self._calculate_entropy(text)
        is_risky = entropy > self.threshold
        
        if is_risky:
            logger.warning(f"⚖️ [Shannon] High entropy detected: {entropy:.2f} (Threshold: {self.threshold})")
            
        return {
            "entropy": entropy,
            "is_risky": is_risky,
            "status": "VETOED" if is_risky else "PASSED"
        }

    def _calculate_entropy(self, text: str) -> float:
        if not text: return 0.0
        prob = [float(text.count(c)) / len(text) for c in dict.fromkeys(list(text))]
        entropy = - sum([p * math.log(p) / math.log(2.0) for p in prob])
        return entropy

if __name__ == "__main__":
    audit = ShannonAudit()
    print(audit.audit("shannon_test_safe_string"))
    print(audit.audit("sk-abcdefghijklmnopqrstuvwxyz0123456789ABCDEF")) # High entropy
