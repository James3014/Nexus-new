import unittest
import sys
import os
from nexus.engine.semantic_adapter import SemanticAdapter
from nexus.engine.capability_contracts import FlowState

class TestOrchestratorBoundary(unittest.TestCase):
    """
    [NEXUS v26] TDD Phase A: Orchestrator Boundary Tests
    驗證 Python Orchestrator 與 Rust Governance 核心的邊界安全性。
    """
    def setUp(self):
        # 確保可以 import 核心模組
        sys.path.append(os.path.abspath("target/release"))
        self.adapter = SemanticAdapter()

    def test_semantic_to_governance_ok(self):
        """正常路徑：模型標籤轉為合法轉移"""
        # 假設當前狀態為 INTAKE (0), 目標 PLAN (1)
        raw = "r:0,d:0,p:1,c:0"
        route, decision, phase, conf = self.adapter.process_model_output(raw)
        
        self.assertEqual(route, "LOCAL")
        self.assertEqual(decision, "ALLOW")
        self.assertEqual(phase, FlowState.PLAN)

    def test_semantic_garbage_falls_back_to_escalate(self):
        """安全路徑：模型輸出垃圾時自動降級"""
        raw = "I see you've provided some input but I cannot classify it."
        route, decision, phase, conf = self.adapter.process_model_output(raw)
        
        self.assertEqual(phase, FlowState.ESCALATE)
        self.assertEqual(decision, "STOP")

    def test_illegal_shortcut_blocked_by_bridge(self):
        """防禦路徑：即便模型建議非法跳步，Bridge 也應拒絕"""
        from nexus.engine.governance_bridge import GovernanceBridge
        bridge = GovernanceBridge()
        
        # 禁止從 INTAKE (S) 直接跳到 CLOSE (C)
        self.assertFalse(bridge.can_transition("INTAKE", "CLOSE"))

if __name__ == "__main__":
    unittest.main()
