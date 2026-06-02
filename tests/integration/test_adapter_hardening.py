import unittest
import sys
import os
from nexus.engine.semantic_adapter import SemanticAdapter
from nexus.engine.capability_contracts import FlowState

class TestAdapterFailClosed(unittest.TestCase):
    """
    [NEXUS v2.4] TDD Phase A: Adapter Failure Classification
    驗證三段式管道：TagEmitter -> GrammarGuard -> EscalationPolicy
    """
    def setUp(self):
        sys.path.append(os.path.abspath("target/release"))
        self.adapter = SemanticAdapter()

    def test_natural_language_leakage_blocked(self):
        """風險 1: 拒絕自然語言洩漏，強制降級至 ESCALATE"""
        raw = "I am a helpful assistant and I think we are in Phase D."
        _, decision, phase, _ = self.adapter.process_model_output(raw)
        
        self.assertEqual(decision, "STOP", "Natural language must trigger STOP decision.")
        self.assertEqual(phase, FlowState.ESCALATE, "Drifted output must route to ESCALATE.")

    def test_broken_tag_handling(self):
        """風險 1: 拒絕半合法標籤 (如 r:0, d:1 無 p 欄位)"""
        raw = "r:0,d:1" # 缺少必要欄位
        _, _, phase, _ = self.adapter.process_model_output(raw)
        self.assertEqual(phase, FlowState.ESCALATE)

    def test_consistency_drift_detection_mock(self):
        """風險 2: 模擬一致性偏移測試 (Consistency Harness 預演)"""
        # 同一輸入，不同輸出，驗證穩定性
        runs = ["r:0,d:0,p:1", "r:0,d:0,p:1", "r:0,d:0,p:2"] # 發生偏移
        results = [self.adapter.process_model_output(r)[2] for r in runs]
        
        is_consistent = all(x == results[0] for x in results)
        self.assertFalse(is_consistent, "Harness must detect inconsistent phase output across runs.")

if __name__ == "__main__":
    unittest.main()
