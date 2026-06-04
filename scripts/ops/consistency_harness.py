import sys
import os
import json
import statistics
from typing import List, Dict

# [NEXUS v2.4] Consistency Harness
# Goal: Measure label stability of 7B/14B models.

class ConsistencyHarness:
    def __init__(self, adapter):
        self.adapter = adapter

    def measure_consistency(self, raw_input: str, trials: int = 5) -> Dict:
        """
        對同一模型輸出進行多跑一致性測試。
        此處模擬模型輸出，實際使用時需對接真/Mock LLM。
        """
        outputs = []
        for _ in range(trials):
            # 模擬模型隨機性
            # 實際應用中此處調用 LLM
            res = self.adapter.process_model_output(raw_input)
            outputs.append(str(res[2])) # 紀錄 Phase

        unique_count = len(set(outputs))
        score = 1.0 / unique_count
        
        return {
            "input": raw_input,
            "trials": trials,
            "consistency_score": score,
            "is_stable": score == 1.0
        }

if __name__ == "__main__":
    sys.path.append(os.path.abspath("target/release"))
    from nexus.engine.semantic_adapter import SemanticAdapter
    harness = ConsistencyHarness(SemanticAdapter())
    
    # 測試穩定輸入
    print("Stability Check (Stable):", harness.measure_consistency("r:0,d:0,p:1,c:0"))
    # 測試不穩定輸入
    print("Stability Check (Unstable):", harness.measure_consistency("invalid_junk"))
