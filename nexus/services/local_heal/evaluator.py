from typing import Dict, Any

class PatchTreeEvaluator:
    """決策與補丁評估引擎，維護修復狀態樹，決定是否需要 Rollback 與剪枝"""
    
    def __init__(self):
        # 追蹤最佳修復記錄與嘗試路徑
        self.best_failed_count = 0  # 初始狀態基線錯誤為 0 (測試預期)
        self.attempts = []

    def evaluate_attempt(self, failed_test_count: int, patch_hash: str) -> Dict[str, Any]:
        self.attempts.append({
            "hash": patch_hash,
            "failed_count": failed_test_count
        })
        
        # 若錯誤數量大於最佳基準（退步），執行回滾
        if failed_test_count > self.best_failed_count:
            return {
                "action": "rollback",
                "reason": f"Regression detected: {failed_test_count} failed tests, best baseline is {self.best_failed_count}"
            }
        
        # 若錯誤數量等於或小於最佳基準，更新最佳狀態並接受
        self.best_failed_count = failed_test_count
        return {
            "action": "accept",
            "reason": f"Improvement or parity: {failed_test_count} failed tests"
        }
