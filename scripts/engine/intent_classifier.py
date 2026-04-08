import logging
from scripts.ops.feynman_bridge import ComplexityRouter

logger = logging.getLogger(__name__)

class IntentClassifier:
    """
    🧠 Nexus 意圖預分類器 (v22 Neural)
    在 Plan 階段進行語義預掃描，精準鎖定治理模式。
    """
    def __init__(self):
        self.feynman_router = ComplexityRouter()

    SPEC_PATTERNS = ["建 UI", "API 名稱", "數據來源", "驗收標準", "規格", "spec"]
    RESEARCH_PATTERNS = ["研究", "research", "探討", "算法", "arxiv"]
    REFATOR_PATTERNS = ["重構", "refactor", "優化結構"]
    
    SPEC_QUESTIONNAIRE = [
        "1. API 名稱？",
        "2. 數據來源 (manifest.json path)？",
        "3. UI 狀態 (loading/success/error)？",
        "4. 驗收標準 (公式)？"
    ]

    def classify(self, task: str) -> dict:
        """物理識別任務意圖"""
        task_lower = task.lower()
        
        # 🧪 Feynman Route Decision
        feynman_decision, _ = self.feynman_router.route_task({
            "id": "intent_scan",
            "type": "research" if any(p in task_lower for p in self.RESEARCH_PATTERNS) else "bug",
            "complexity": "high" if "arch" in task_lower or "spec" in task_lower else "low"
        })

        # 0. SPEC_MODE 優先識別 (Work Order 1)
        if any(p in task_lower for p in self.SPEC_PATTERNS):
            logger.info("🎯 [Classifier] Intent: SPEC_MODE")
            return {
                "mode": "spec_mode",
                "intent": "spec_mode",
                "feynman_path": feynman_decision,
                "questionnaire": self.SPEC_QUESTIONNAIRE
            }

        # 1. 重構意圖識別
        if any(p in task_lower for p in self.REFATOR_PATTERNS):
            logger.info("🎯 [Classifier] Intent: REFACTOR_TEMPLATE")
            return {"mode": "default", "intent": "refactor_template", "feynman_path": feynman_decision}
        
        # 2. 研究意圖識別
        if any(p in task_lower for p in self.RESEARCH_PATTERNS):
            logger.info("🎯 [Classifier] Intent: RESEARCH_TEMPLATE")
            return {"mode": "default", "intent": "research_template", "feynman_path": feynman_decision}
        
        # 3. 預設模式
        return {"mode": "default", "intent": "default", "feynman_path": feynman_decision}

    def get_bias_rules(self, intent: str) -> dict:
        """獲取特定意圖的治理偏見"""
        if intent == "refactor_template":
            return {
                "commit_limit": 100,
                "srp_mandatory": True,
                "decouple_mode": "strict"
            }
        return {}
