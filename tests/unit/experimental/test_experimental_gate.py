import unittest
from nexus.experimental.sandboxed_adapter import SandboxedAdapter
class TestExperimental(unittest.TestCase):
    def test_sandbox(self):
        with self.assertRaises(PermissionError):
            SandboxedAdapter(False).execute()
