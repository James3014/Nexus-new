import unittest
import sys
import os
from nexus.engine.semantic_adapter import SemanticAdapter
from nexus.engine.flow_control import FlowStateMachine
from nexus.engine.capability_contracts import FlowState

class FakeModel:
    """模擬不同量級的模型輸出"""
    def __init__(self, size_label):
        self.size_label = size_label
    
    def suggest(self, scenario):
        # 模擬 7B/14B 雖然推理能力不同，但均輸出相同的治理標籤
        mapping = {
            "happy_path": "r:0,d:0,p:1,c:0",
            "attack": "r:0,d:2,p:6,c:1",
            "drift": "I am hallucinating some medical advice here..."
        }
        return mapping.get(scenario, "unknown")

class TestModelAgnosticGovernance(unittest.TestCase):
    """
    [NEXUS v2.1] Contract Test: Model Agnostic Governance
    驗證更換模型不影響治理核心的裁決結果。
    """
    def setUp(self):
        sys.path.append(os.path.abspath("target/release"))
        self.adapter = SemanticAdapter()
        self.fsm = FlowStateMachine()

    def test_governance_result_is_same_across_models(self):
        """核心測試：無論模型量級，只要標籤一致，治理結果必須一致"""
        models = [FakeModel("7B"), FakeModel("14B"), FakeModel("70B")]
        
        for model in models:
            raw = model.suggest("happy_path")
            _, _, target_phase, _ = self.adapter.process_model_output(raw)
            allowed = self.fsm.validate_transition(FlowState.INTAKE, target_phase)
            
            print(f"[{model.size_label}] Input: {raw} -> Allowed: {allowed}")
            self.assertTrue(allowed, f"Model {model.size_label} failed happy path")
            self.assertEqual(target_phase, FlowState.PLAN)

    def test_hallucination_protection_is_constant(self):
        """防禦測試：無論模型幻覺多嚴重，治理核心必須保持 Fail-Closed"""
        model = FakeModel("HUC")
        raw = model.suggest("drift")
        _, _, target_phase, _ = self.adapter.process_model_output(raw)
        
        # 幻覺應被 Normalizer 攔截並轉為 Escalate
        self.assertEqual(target_phase, FlowState.ESCALATE)
        allowed = self.fsm.validate_transition(FlowState.INTAKE, target_phase)
        self.assertTrue(allowed) # 逃生艙應始終可用

if __name__ == "__main__":
    unittest.main()
