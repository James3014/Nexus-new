import unittest
from nexus.telemetry.telemetry_models import TelemetryBundle

class TestTelemetryContract(unittest.TestCase):
    def test_partial_fields_marks_incomplete(self):
        # 缺 token_usage
        bundle = TelemetryBundle(wall_time_ms=100, token_usage=None, provider_costs=0.01, overhead_ms=10)
        self.assertFalse(bundle.complete)

    def test_all_fields_marks_complete(self):
        bundle = TelemetryBundle(wall_time_ms=100, token_usage=500, provider_costs=0.01, overhead_ms=10)
        self.assertTrue(bundle.complete)

if __name__ == "__main__":
    unittest.main()
