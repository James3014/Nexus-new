import unittest
from nexus.governance.udl_engine import UDLEngine
class TestUDL(unittest.TestCase):
    def test_health_stable(self):
        h = UDLEngine.calculate_health(1.0, 1.0, True, True)
        self.assertEqual(h.status, 'STABLE')
        self.assertEqual(h.score, 1.0)
