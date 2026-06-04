import unittest
from nexus.policy.versioning import PolicyVersioner
class TestVersioning(unittest.TestCase):
    def test_version(self): self.assertEqual(PolicyVersioner('v1').version, 'v1')
