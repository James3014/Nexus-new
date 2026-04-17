import unittest
from pathlib import Path
from nexus.core.mem_palace import MemoryPalace

class TestMemoryPalace(unittest.TestCase):
    def test_audit_logic(self):
        palace = MemoryPalace()
        self.assertTrue(palace.audit_action("D", "Check evidence in LDB"))
        self.assertFalse(palace.audit_action("D", "Just guessing"))
