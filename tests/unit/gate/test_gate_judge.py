import unittest
from nexus.gate.gate_judge import GateJudge
from nexus.replay.replay_artifact import ReplayArtifact
from nexus.telemetry.telemetry_models import TelemetryBundle

class TestGateJudgePurity(unittest.TestCase):
    def test_gate_fails_closed_when_telemetry_missing(self):
        # 傳入 incomplete telemetry
        t = TelemetryBundle(None, None, None, None)
        res = GateJudge.decide("t1", telemetry=t)
        self.assertFalse(res["allowed"])
        self.assertEqual(res["blocker"], "INCOMPLETE_TELEMETRY")

    def test_gate_fails_when_replay_missing(self):
        t = TelemetryBundle(100, 100, 0.1, 10)
        res = GateJudge.decide("t1", telemetry=t, replay=None)
        self.assertFalse(res["allowed"])
        self.assertEqual(res["blocker"], "MISSING_REPLAY_EVIDENCE")

if __name__ == "__main__":
    unittest.main()
