import unittest
from nexus.governance.loop_monitor import LoopMonitor
class TestLoop(unittest.TestCase):
    def test_oscillation(self):
        history = [1.0, 0.2, 0.9, 0.1]
        self.assertTrue(LoopMonitor.detect_oscillation(history))
