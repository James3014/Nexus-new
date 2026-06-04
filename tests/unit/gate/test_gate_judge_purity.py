import unittest
from nexus.gate.gate_judge import GateJudge, BlockerCodes
from nexus.replay.replay_artifact import ReplayArtifact
from nexus.telemetry.telemetry_models import TelemetryBundle

class TestGateJudgePurity(unittest.TestCase):
    def test_gate_is_pure_for_same_inputs(self):
        t = TelemetryBundle(100, 100, 0.1, 10)
        r = ReplayArtifact("t1", "SUCCESS", "pytest", "/tmp", 60, [])
        
        res1 = GateJudge.decide("t1", telemetry=t, replay=r)
        res2 = GateJudge.decide("t1", telemetry=t, replay=r)
        
        self.assertEqual(res1, res2)

    def test_gate_returns_explicit_blocker_code(self):
        t = TelemetryBundle(100, 100, 0.1, 10)
        # 模擬失敗的 Replay
        r = ReplayArtifact("t1", "FAILURE", "pytest", "/tmp", 60, ["failed"])
        
        res = GateJudge.decide("t1", telemetry=t, replay=r)
        self.assertFalse(res["allowed"])
        self.assertEqual(res["blocker"], BlockerCodes.REPLAY_FAILURE)

if __name__ == "__main__":
    unittest.main()
