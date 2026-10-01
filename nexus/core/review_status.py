from typing import Any, Dict, List, Optional, Tuple

class ReviewStatusNormalizer:
    @staticmethod
    def normalize(status: str) -> Tuple[str, bool]:
        """Normalize reviewer output without conflating a block and a disposition."""
        status = str(status).upper().strip()
        
        if status in ["APPROVED", "PASS", "SUCCESS", "APPROVED_WITH_TIPS"]:
            return "APPROVED", True
        
        if status == "SKIPPED_QUOTA":
            return "SKIPPED_QUOTA", True
            
        if status in ["REJECTED", "REJECTED_WITH_REASON"]:
            return "REJECTED", False

        if status in ["FAIL", "FAILED", "REVISE", "RECOVERABLE_BLOCK"]:
            return "RECOVERABLE_BLOCK", False
            
        return "RECOVERABLE_BLOCK", False
