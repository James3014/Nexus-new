import ast
from pathlib import Path
from typing import List, Dict, Set, Any
import logging

logger = logging.getLogger(__name__)

class ValueFlowScorer:
    """
    🛡️ ValueFlowScorer: 資料流加權排序器
    根據反例、失敗符號與依賴關係對代碼片段進行加權。
    """
    
    def __init__(self, criteria_symbols: Set[str]):
        self.criteria = criteria_symbols

    def score_node(self, node: ast.AST, reasons: List[str]) -> float:
        score = 0.0
        name = getattr(node, "name", "")
        
        # 1. 直接命中 (Direct Hit)
        if name in self.criteria:
            score += 5.0
            reasons.append(f"Direct criteria hit: {name}")

        # 2. 資料/控制流分析 (輕量級)
        for child in ast.walk(node):
            # 檢查是否引用了關鍵符號
            if isinstance(child, ast.Name) and child.id in self.criteria:
                score += 3.0
                reasons.append(f"References criteria symbol: {child.id}")
            
            # 檢查是否為控制謂詞 (If/While/For)
            if isinstance(child, (ast.If, ast.While, ast.For)):
                # 若謂詞中包含關鍵符號，權重更高
                for sub in ast.walk(child.test if hasattr(child, "test") else child.iter):
                    if isinstance(sub, ast.Name) and sub.id in self.criteria:
                        score += 2.0
                        reasons.append(f"Controlling logic using {sub.id}")

        return score
