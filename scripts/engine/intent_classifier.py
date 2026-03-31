import logging

logger = logging.getLogger(__name__)

class IntentClassifier:
    """
    🧠 Nexus 意圖預分類器 (v22 Neural)
    在 Plan 階段進行語義預掃描，精準鎖定治理模式。
    """
    REFATOR_PATTERNS = ["重構", "refactor", "clean", "linus", "模組", "解耦", "srp"]
    RESEARCH_PATTERNS = ["研究", "research", "分析", "分析器", "why", "查一下"]

    def classify(self, task: str) -> str:
        """物理識別任務意圖"""
        task_lower = task.lower()
        
        # 1. 重構意圖識別
        if any(p in task_lower for p in self.REFATOR_PATTERNS):
            logger.info("🎯 [Classifier] Intent: REFACTOR_TEMPLATE")
            return "refactor_template"
        
        # 2. 研究意圖識別
        if any(p in task_lower for p in self.RESEARCH_PATTERNS):
            logger.info("🎯 [Classifier] Intent: RESEARCH_TEMPLATE")
            return "research_template"
        
        # 3. 預設模式
        return "default"

    def get_bias_rules(self, intent: str) -> dict:
        """獲取特定意圖的治理偏見"""
        if intent == "refactor_template":
            return {
                "commit_limit": 100,
                "srp_mandatory": True,
                "decouple_mode": "strict"
            }
        return {}
