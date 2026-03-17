from typing import Tuple

class ReviewStatusNormalizer:
    @staticmethod
    def normalize(status: str) -> Tuple[str, bool]:
        """將多樣的 LLM 回傳狀態規範化為系統可識別的狀態與成功旗標"""
        status = str(status).upper().strip()
        
        if status in ["APPROVED", "PASS", "SUCCESS", "APPROVED_WITH_TIPS"]:
            return "APPROVED", True
        
        if status == "SKIPPED_QUOTA":
            return "SKIPPED_QUOTA", True
            
        if status in ["REJECTED", "FAIL", "FAILED", "REJECTED_WITH_REASON"]:
            return "REJECTED", False
            
        return "UNKNOWN", False
