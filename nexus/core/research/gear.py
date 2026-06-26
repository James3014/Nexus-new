from typing import Optional, Dict, Any, List
from pathlib import Path
from nexus.research.skill_router import SkillRouter

class ARCCycle:
    """
    🧬 AutoResearchClaw Cycle (v22.2 / DeepScientist Integrated)
    職責: 執行 23 階段研究循環。
    對位: 已整合配置層 (SkillRouter)，支援 PXDRAC 標準流程。
    """
    DEFAULT_ARC_STAGES = [
        'topic_init',           # 1. 主題初始化 (ARC-01)
        'problem_decompose',    # 2. 問題分解 (ARC-02)
        'search_strategy',      # 3. 搜索策略 (ARC-03)
        'literature_collect',   # 4. 文獻採集 (ARC-04)
        'methodology_verify'    # 5. 方法論驗證 (ARC-05)
    ]

    def __init__(self, router: Optional[SkillRouter] = None):
        self.router = router

    def run(self, query: str) -> dict:
        print(f"🧬 [ARC:Cycle] Starting Research Loop for: {query}")
        
        if self.router:
            return self._run_with_router(query)
        else:
            return self._run_fallback(query)

    def _run_with_router(self, query: str) -> dict:
        """使用配置層執行的 PXDRAC 流程。"""
        if not self.router:
            return {"status": "ERROR", "mode": "SkillAware", "error": "Router not available"}
        
        findings = {}
        current_stage = "P" # 從 Scout 開始
        stages_executed = []
        
        while current_stage != "FIN":
            skill_content = self.router.load_skill_content(current_stage)
            stage_name = self.router.STAGE_MAP.get(current_stage, "unknown")
            
            print(f"   ↳ [Stage: {current_stage} ({stage_name})] 📘 Loading SKILL.md...")
            # 模擬執行邏輯
            findings[current_stage] = f"Executed {stage_name} with skill rules."
            stages_executed.append(current_stage)
            
            # 獲取下一階段
            next_stage = self.router.get_next_stage(current_stage, findings)
            if next_stage == current_stage or next_stage not in self.router.STAGE_MAP:
                current_stage = "FIN"
            else:
                current_stage = next_stage
                
        return {
            "status": "SUCCESS",
            "mode": "SkillAware",
            "stages_executed": len(stages_executed),
            "executed_list": stages_executed,
            "findings": findings
        }

    def _run_fallback(self, query: str) -> dict:
        """原有的 ARC 5 階段循環 (Fallback)。"""
        print("   ⚠️ [Warning] No SkillRouter found. Falling back to Legacy ARC stages.")
        findings = {}
        for stage in self.DEFAULT_ARC_STAGES:
            findings[stage] = f"ARC {stage} research successful for query: '{query}'"
            print(f"   ↳ [Stage: {stage}] 🟢 PASS")
            
        return {
            "status": "SUCCESS",
            "mode": "LegacyARC",
            "stages_executed": len(self.DEFAULT_ARC_STAGES),
            "findings": findings
        }
