import unittest
import sys
import os
from nexus.engine.semantic_adapter import SemanticAdapter
from nexus.engine.capability_contracts import FlowState

class TestSemanticIsolation(unittest.TestCase):
    """
    [NEXUS v2.2] Contract Test: Semantic Isolation
    驗證模型幻覺（回聲效應、自然語言、空輸出）被物理隔離在治理核心外。
    """
    def setUp(self):
        sys.path.append(os.path.abspath("target/release"))
        self.adapter = SemanticAdapter()

    def test_echo_effect_isolation(self):
        """幻覺測試：模型將 Prompt 直接搬運到輸出 (回聲效應)"""
        raw = "I see you want to transition from D to R. Based on your input..."
        _, decision, phase, _ = self.adapter.process_model_output(raw)
        
        # 應被 Normalizer 拒絕並安全降級
        self.assertEqual(decision, "STOP")
        self.assertEqual(phase, FlowState.ESCALATE)

    def test_natural_language_refusal(self):
        """幻覺測試：模型給出擬人化的解釋而非標籤"""
        raw = "The task is done, you can now proceed to review."
        _, decision, phase, _ = self.adapter.process_model_output(raw)
        
        self.assertEqual(decision, "STOP")
        self.assertEqual(phase, FlowState.ESCALATE)

    def test_empty_or_broken_output(self):
        """極限測試：模型輸出為空或不完整標籤"""
        for broken in ["", "r:0", "p:1, d:allow"]:
            _, decision, phase, _ = self.adapter.process_model_output(broken)
            self.assertEqual(phase, FlowState.ESCALATE)

    def test_valid_label_precision(self):
        """基礎測試：極簡標籤應被精確解析"""
        raw = "r:0,d:0,p:3,c:0" # Local, Allow, Execute, High
        route, decision, phase, conf = self.adapter.process_model_output(raw)
        
        self.assertEqual(route, "LOCAL")
        self.assertEqual(decision, "ALLOW")
        self.assertEqual(phase, FlowState.EXECUTE)

if __name__ == "__main__":
    unittest.main()
