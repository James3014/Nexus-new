import unittest
from pathlib import Path
from nexus.core.belief_engine import BeliefEngine

class TestBeliefEngine(unittest.TestCase):
    def test_update_and_retrieve(self):
        engine = BeliefEngine(Path("test_belief.json"))
        engine.update_belief("task-1", "PROT-DRIFT", 0.95, "EV-123")
        self.assertEqual(engine.assess_confidence("task-2", "PROT-DRIFT"), 0.95)
        if Path("test_belief.json").exists(): Path("test_belief.json").unlink()
