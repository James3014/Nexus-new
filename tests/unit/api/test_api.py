import unittest
from nexus.api.control_plane_api import GovernanceAPI
class TestAPI(unittest.TestCase):
    def test_status(self): self.assertEqual(GovernanceAPI().get_status()['status'], 'UP')
