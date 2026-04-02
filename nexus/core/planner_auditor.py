from typing import Any, Dict, List, Optional, Tuple
import re
import logging

logger = logging.getLogger(__name__)

class PlannerAuditor:
    """🎯 Nexus 計畫審計員：核驗 Phase P 的思維密度與物理真值節點"""

    REQUIRED_NODES = {
        "probe": r"\[Probe\]",    # 物理探針 (TruthValidator/Preflight)
        "surface": r"\[Surface\]", # 代碼影響表面積
        "rollback": r"\[Rollback\]" # 失敗回滾與清理 SOP
    }

    @staticmethod
    def audit_plan(plan_text: str) -> Dict[str, Any]:
        """🎯 掃描計畫本文，計算思維深度與密度分"""
        findings = {}
        found_count = 0
        
        for node, pattern in PlannerAuditor.REQUIRED_NODES.items():
            match = re.search(pattern, plan_text, re.IGNORECASE)
            findings[node] = bool(match)
            if match:
                found_count += 1
        
        # 計算密度：節點覆蓋率
        density = found_count / len(PlannerAuditor.REQUIRED_NODES)
        
        # 深思度：除了標籤，還需核驗內文長度
        # 簡單邏輯：若標籤後緊跟內容（非空），則得分
        depth_score = density
        if len(plan_text.split()) < 100:
            depth_score *= 0.5 # 太短也視為思維淺薄
            
        status = "HEALTHY" if density >= 0.6 else "INSUFFICIENT_THOUGHT"
        
        logger.info(f"🔍 [Planner:Audit] Density: {density:.2f}, Status: {status}")
        
        return {
            "density_score": density,
            "thinking_depth_score": depth_score,
            "findings": findings,
            "status": status
        }

if __name__ == "__main__":
    test_plan = """
    # 計畫
    [Probe]: 核驗 localhost:8000
    [Surface]: 修改 scoring.py
    [Rollback]: git checkout .
    """
    print(PlannerAuditor.audit_plan(test_plan))
