import unittest
import sys
import os
from nexus.engine.semantic_adapter import SemanticAdapter
from nexus.engine.flow_control import FlowStateMachine
from nexus.engine.capability_contracts import FlowState

class TestE2EHybridGovernance(unittest.TestCase):
    """
    [NEXUS v26] End-to-End Regression Tests for Hybrid Governance 2.0
    驗證從模型語義到 Rust 裁決的全鏈路穩定性。
    """
    def setUp(self):
        sys.path.append(os.path.abspath("target/release"))
        self.fsm = FlowStateMachine()
        self.adapter = SemanticAdapter()

    def test_e2e_happy_path(self):
        """正常流程：INTAKE -> PLAN"""
        raw = "r:0,d:0,p:1,c:0" # 模型建議 P
        route, decision, target_phase, conf = self.adapter.process_model_output(raw)
        
        # Rust 裁決
        allowed = self.fsm.validate_transition(FlowState.INTAKE, target_phase)
        self.assertTrue(allowed)
        self.assertEqual(target_phase, FlowState.PLAN)

    def test_e2e_illegal_jump_blocked(self):
        """非法流程：INTAKE -> CLOSE (被 Rust 攔截)"""
        raw = "r:0,d:0,p:4,c:0" # 模型建議 C (非法跳步)
        route, decision, target_phase, conf = self.adapter.process_model_output(raw)
        
        # Rust 裁決
        allowed = self.fsm.validate_transition(FlowState.INTAKE, target_phase)
        self.assertFalse(allowed)

    def test_e2e_hallucination_handled(self):
        """模型幻覺：輸出垃圾文字"""
        raw = "Error occurred, please check logs."
        route, decision, target_phase, conf = self.adapter.process_model_output(raw)
        
        # 應自動降級為 ESCALATE
        self.assertEqual(target_phase, FlowState.ESCALATE)
        # Rust 應允許進入 ESCALATE 狀態（逃生艙機制）
        allowed = self.fsm.validate_transition(FlowState.INTAKE, target_phase)
        self.assertTrue(allowed)

if __name__ == "__main__":
    unittest.main()
