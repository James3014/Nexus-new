import json
from typing import Dict, Any, List

class DecisionFormulaEngine:
    """
    🧮 Work Order D: Decision Formula Engine
    將關鍵判斷從散文敘述變成公式化規則，確保 UI 與 Agent 判定一致。
    """

    FORMULAS = {
        "can_publish": "acceptancePassed && auditPassed",
        "is_terminal": "status in ['crystalized', 'failed', 'verifyFatal']",
        "needs_human_intervention": "status in ['TIMEOUTSTALLED', 'TAMPERED']",
        "show_red_alert": "severity == 'critical' or status == 'failed'"
    }

    def __init__(self, context: Dict[str, Any]):
        """
        context 應包含歸一化後的狀態與真值數據。
        """
        self.context = context

    def evaluate(self) -> Dict[str, bool]:
        """
        執行公式判定。
        注意：這裡使用簡單的邏輯模擬，實際可升級為複雜表達式解析。
        """
        results = {}
        ctx = self.context
        
        # 模擬 can_publish 判定
        results["can_publish"] = ctx.get("acceptancePassed", False) and ctx.get("auditPassed", False)
        
        # 模擬 is_terminal 判定
        results["is_terminal"] = ctx.get("status") in ['crystalized', 'failed', 'verifyFatal']
        
        # 模擬 needs_intervention 判定
        results["needs_intervention"] = ctx.get("status") in ['TIMEOUTSTALLED', 'TAMPERED']
        
        return results

    def generate_artifact(self) -> Dict[str, Any]:
        """產出實作包所需的公式表"""
        return {
            "formulas": self.FORMULAS,
            "version": "v1.0"
        }

if __name__ == "__main__":
    # 測試
    mock_ctx = {"acceptancePassed": True, "auditPassed": True, "status": "running"}
    engine = DecisionFormulaEngine(mock_ctx)
    print(f"Context: {mock_ctx}")
    print(f"Evaluation: {engine.evaluate()}")
