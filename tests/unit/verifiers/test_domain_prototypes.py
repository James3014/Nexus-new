import unittest
from nexus.verifiers.domain.name_sanity import NameSanityVerifier
from nexus.verifiers.domain.inheritance import DeepInheritanceVerifier

class TestDomainVerifiers(unittest.TestCase):
    def test_name_sanity_interception(self):
        patch = "result = np.arange(10)" # 無 import
        v = NameSanityVerifier.evaluate("c1", patch)
        self.assertFalse(v.passed)
        self.assertEqual(v.blocker_code, "NAME_ERROR")

    def test_inheritance_guard(self):
        patch = "def __getattr__(self, name): return self.other" # 漏掉 super
        v = DeepInheritanceVerifier.evaluate("c1", patch)
        self.assertFalse(v.passed)
        self.assertEqual(v.blocker_code, "MRO_RISK")

if __name__ == "__main__":
    unittest.main()
