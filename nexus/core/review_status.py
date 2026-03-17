from typing import Tuple

class ReviewStatusNormalizer:
    @staticmethod
    def normalize(status: str) -> Tuple[str, bool]:
        """將多樣的 LLM 回傳狀態規範化為系統可識別的狀態與成功旗標"""
        status = str(status).upper().strip()
        
        if status in ["APPROVED", "SKIPPED_QUOTA", "PASS"]:
            return status, True
        
        if status == "BEST_ANSWER":
            return "BEST_ANSWER", True
            
        if status in ["REJECTED", "FAIL", "FAILED"]:
            return "REJECTED", False
            
        return "UNKNOWN", False
