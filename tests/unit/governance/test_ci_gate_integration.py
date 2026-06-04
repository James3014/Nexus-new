import unittest
import os
from nexus.ci.ci_gate import CIGate
from nexus.evaluation.manifest_manager import ManifestManager

class TestCIGateSprint4(unittest.TestCase):
    """[v27.1 Sprint 4] CI Gate Production Integration TDD"""

    def test_observation_mode_blocks_land(self):
        """[P1] 驗證：觀測模式下應阻斷晉升"""
        os.environ["NEXUS_GOVERNANCE_MODE"] = "OBSERVATION"
        res = CIGate.evaluate_land_readiness({"manifest_hash": "any"})
        self.assertFalse(res)
        
    def test_drift_blocks_land(self):
        """[P1] 驗證：雜湊漂移時應阻斷晉升"""
        if "NEXUS_GOVERNANCE_MODE" in os.environ:
            del os.environ["NEXUS_GOVERNANCE_MODE"]
            
        res = CIGate.evaluate_land_readiness({"manifest_hash": "dirty-hash"})
        self.assertFalse(res)

if __name__ == "__main__":
    unittest.main()
