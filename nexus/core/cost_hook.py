from typing import Any, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class BudgetExceededError(Exception):
    """當預估成本超過剩餘預算時拋出"""
    pass

class CostHook:
    """
    💰 Nexus 成本感知鉤子 (AOS-P5.9)
    負責 Token 預算的精準控制與任務執行前的「成本預判」。
    """
    
    # 物理模式矩陣：指令 -> 基礎 Token 消耗
    COST_MODEL = {
        "read_file": 100,
        "rg_search": 200,
        "edit_file": 800,
        "safe_patch": 900,
        "run_test": 1500,
        "nexus:probe-deps": 400,
        "nexus:runner": 1200
    }

    def predict_cost(self, cmd: str, params: Dict[str, Any]) -> int:
        """🎯 依據指令與規模預計成本 (Claw-30P4 遞迴增益)"""
        from nexus.core.recursive_cost import RecursiveCost
        recursive = RecursiveCost.estimate_tree(cmd, params)
        if recursive > 0:
            return recursive
            
        base = self.COST_MODEL.get(cmd, 150)
        
        # 規模修正 (例如掃描檔案數)
        if "files" in params:
            base += len(params["files"]) * 50
        if "target_file" in params:
            base += 300 # 編輯特定檔案通常涉及 Context 回傳
            
        return base

    def budget_check(self, predicted: int, remaining: int) -> str:
        """⚖️ 執行預算攔截邏輯"""
        if predicted > remaining:
            logger.error(f"🛑 [CostHook] Budget Exceeded! Predicted {predicted} > Remaining {remaining}")
            return "BLOCKED"
            
        if predicted > remaining * 0.7:
            logger.warning(f"⚠️ [CostHook] High Cost Alert! {predicted} will consume >70% of budget.")
            return "WARN_OPTIMIZE"
            
        return "OK"
