from enum import Enum, auto
from typing import List, Dict, Any

class ApplyStrategy(str, Enum):
    EXACT = "EXACT"
    WHITESPACE_TOLERANT = "WHITESPACE_TOLERANT"
    BOUNDED_FUZZY = "BOUNDED_FUZZY"
    LINE_BY_LINE = "LINE_BY_LINE"

class ApplyPlanner:
    """
    🛡️ ApplyPlanner: 套用計畫器
    將 SoC 套用於套用策略。決定執行順序與預算。
    """
    def __init__(self, max_fuzzy_drift: int = 50, edit_budget: int = 1000):
        self.max_fuzzy_drift = max_fuzzy_drift
        self.edit_budget = edit_budget

    def get_execution_plan(self) -> List[ApplyStrategy]:
        return [
            ApplyStrategy.EXACT,
            ApplyStrategy.WHITESPACE_TOLERANT,
            ApplyStrategy.BOUNDED_FUZZY
        ]
