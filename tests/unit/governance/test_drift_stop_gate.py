import unittest
from nexus.governance.application.drift_stop_gate import DriftStopGate
from nexus.evaluation.manifest_manager import ManifestManager

class TestDriftStopGate(unittest.TestCase):
    """[v27.1 Sprint 3] Drift Stop Gate TDD"""
    
    def test_manifest_hash_drift_blocks(self):
        """[P0] 驗證：雜湊不一致時阻斷"""
        real_hash = ManifestManager.get_manifest_hash()
        fake_hash = "dirty-hash-123"
        
        self.assertFalse(DriftStopGate.verify_alignment(fake_hash))
        self.assertTrue(DriftStopGate.verify_alignment(real_hash))

if __name__ == "__main__":
    unittest.main()
