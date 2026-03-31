import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class RefactorGovernance:
    """
    🖋️ Nexus 重構治理器 (v22 Linus Mode)
    物理注入偏見規則，確保架構解耦。
    """
    LINUS_RULES = {
        "small_commits": "Maintain <100 lines per commit.",
        "srp": "Single Responsibility Principle (1 file, 1 responsibility).",
        "decouple": "Zero god functions. Decouple DB from Business Logic."
    }

    @staticmethod
    def generate_refactor_plan(task_id: str, codebase_path: str) -> List[Dict]:
        """🧬 根據治理規則生成漸進式重構 DAG"""
        logger.info("📐 [Refactor] Generating Hardened Plan (v22-Linus)...")
        return [
            {
                "id": f"{task_id}_P1",
                "desc": "拆分核心模組：將大型模組分散至子模組路徑。",
                "rule": "SRP"
            },
            {
                "id": f"{task_id}_P2",
                "desc": "解耦依賴層：隔離資料庫存取層與實體邏輯。",
                "rule": "Decouple"
            },
            {
                "id": f"{task_id}_P3",
                "desc": "結算驗收：執行圈複雜度測評與一致性 Audit。",
                "rule": "CleanCode"
            }
        ]

    @staticmethod
    def get_linus_bias() -> str:
        """獲取治理偏見 Prompt 片段"""
        return "\n".join([f"- {k}: {v}" for k, v in RefactorGovernance.LINUS_RULES.items()])

