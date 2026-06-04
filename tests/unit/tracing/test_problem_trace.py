import unittest
from nexus.tracing.problem_trace import ProblemTrace
class TestTrace(unittest.TestCase):
    def test_trace(self):
        t = ProblemTrace('t1')
        t.record('ingress', 'created', source='swe-bench')
        self.assertEqual(len(t.steps), 1)
