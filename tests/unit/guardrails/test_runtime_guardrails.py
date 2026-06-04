import unittest
from nexus.guardrails.runtime_guardrails import RuntimeGuardrail
class TestGuardrails(unittest.TestCase):
    def test_readonly(self):
        with self.assertRaises(PermissionError):
            RuntimeGuardrail.enforce_readonly("f = open('test', 'w')")
