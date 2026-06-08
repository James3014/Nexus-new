from typing import List, Dict, Any

class SwarmCompare:
    """
    🛡️ SwarmCompare: 候選品質比較器
    基於 Audit Pass、約束覆蓋率與 Token 成本進行排序。
    執行 Fail-Closed 治理。
    """
    def compare_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        排序分支候選。
        排序規則：
        1. 修復計畫完整度 (passed=True)
        2. 自我信心得分 (score)
        3. 語義標籤 (semantic_reasoning_ceiling)
        """
        # 過濾完全不符合契約的分支
        valid_candidates = [c for c in candidates if c.get("passed")]
        
        if not valid_candidates:
            return []

        # 基礎排序
        sorted_list = sorted(
            valid_candidates, 
            key=lambda x: (x.get("score", 0.0)), 
            reverse=True
        )
        
        # 標記排名
        for i, cand in enumerate(sorted_list):
            cand["rank"] = i + 1
            
        return sorted_list

    def select_best(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """選擇最佳候選，若無可用則拋出異常。"""
        ranked = self.compare_candidates(candidates)
        if not ranked:
            raise RuntimeError("NO_VIABLE_SWARM_CANDIDATE: All branches failed plan contract.")
        return ranked[0]
