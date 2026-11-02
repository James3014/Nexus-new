import unittest
import os
from unittest import mock
from nexus.ci.ci_gate import CIGate
from nexus.evaluation.manifest_manager import ManifestManager

class TestCIGateSprint4(unittest.TestCase):
    """[v27.1 Sprint 4] CI Gate Production Integration TDD"""

    def _isolate_env(self):
        """Put os.environ back to its pre-test contents when the test ends."""
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_observation_mode_blocks_land(self):
        """[P1] 驗證：觀測模式下應阻斷晉升"""
        self._isolate_env()
        os.environ["NEXUS_GOVERNANCE_MODE"] = "OBSERVATION"
        res = CIGate.evaluate_land_readiness({"manifest_hash": "any"})
        self.assertFalse(res)
        
    def test_drift_blocks_land(self):
        """[P1] 驗證：雜湊漂移時應阻斷晉升"""
        self._isolate_env()
        os.environ.pop("NEXUS_GOVERNANCE_MODE", None)
            
        res = CIGate.evaluate_land_readiness({"manifest_hash": "dirty-hash"})
        self.assertFalse(res)

if __name__ == "__main__":
    unittest.main()
