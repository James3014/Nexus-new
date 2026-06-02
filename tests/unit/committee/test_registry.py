import unittest
from nexus.committee.models import ProposalCandidate
from nexus.committee.registry import CandidateRegistry

class TestCandidateRegistry(unittest.TestCase):
    def test_registry_registration(self):
        registry = CandidateRegistry("task-01")
        c = ProposalCandidate("c1", "7B", 1, "r:0", "PLAN", [])
        registry.register(c)
        self.assertEqual(registry.size(), 1)

    def test_duplicate_rejection(self):
        registry = CandidateRegistry("task-01")
        c = ProposalCandidate("c1", "7B", 1, "r:0", "PLAN", [])
        registry.register(c)
        with self.assertRaises(ValueError):
            registry.register(c)

if __name__ == "__main__":
    unittest.main()
