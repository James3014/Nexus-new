import unittest
from pathlib import Path
from unittest.mock import MagicMock
from nexus.core.orchestrator import NexusOrchestrator
from nexus.core.config import OrchestratorConfig

class TestOrchestratorPentadIntegration(unittest.TestCase):
    def test_pentad_logic_invocation(self):
        # 1. Setup mock config and hubs
        config = OrchestratorConfig(task="Test Pentad", skill_id="test-v25", mode="audit")
        infra = MagicMock()
        intel = MagicMock()
        gov = MagicMock()
        
        # 2. Initialize Orchestrator (it should auto-inject BeliefEngine & MemoryPalace)
        orch = NexusOrchestrator(config, infra, intel, gov)
        
        # 3. Mock LLM response for D/R phase trigger
        intel.llm.ask_with_template.return_value = ({"status": "PASS", "summary": "Integrated evidence", "confidence": 0.9}, "raw_text")
        
        # 4. Spying on Palace and Belief Engine
        orch.palace.audit_action = MagicMock(return_value=True)
        orch.belief_engine.assess_confidence = MagicMock(return_value=1.0)
        
        # 5. Execute sequence
        # We simulate the git changes to enter the loop
        infra.git.get_changes.return_value = (["file.py"], "diff_text")
        
        orch._do_loop()
        
        # 6. Assertions: Verify dual calling of Pentad gates
        orch.palace.audit_action.assert_called_with("D", "Integrated evidence")
        orch.belief_engine.assess_confidence.assert_called()
        print("✅ Orchestrator Integration: Pentad gates verified.")

if __name__ == "__main__":
    unittest.main()
