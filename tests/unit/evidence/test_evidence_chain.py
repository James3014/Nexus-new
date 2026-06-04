import unittest
from nexus.evidence.evidence_chain_service import EvidenceChainService

class TestEvidenceChain(unittest.TestCase):
    def test_seal_generates_stable_sha256(self):
        payload = {"result": "PASS", "task": "t1"}
        s1 = EvidenceChainService.seal("e1", payload)
        s2 = EvidenceChainService.seal("e1", payload)
        
        self.assertEqual(s1["fingerprint"], s2["fingerprint"])
        self.assertTrue(s1["sealed"])

    def test_verify_rejects_hash_mismatch(self):
        payload = {"result": "PASS"}
        s1 = EvidenceChainService.seal("e1", payload)
        
        # 篡改 Payload
        tampered_seal = s1.copy()
        tampered_seal["payload"] = {"result": "FAIL"}
        
        self.assertFalse(EvidenceChainService.verify(tampered_seal))

    def test_barrier_blocks_partial_telemetry(self):
        s1 = EvidenceChainService.seal("e1", {"data": "ok"})
        res = EvidenceChainService.barrier(s1, partial_telemetry=True, dirty_write=False)
        self.assertEqual(res["status"], "BLOCKED")
        self.assertEqual(res["reason"], "PARTIAL_TELEMETRY_DETECTED")

if __name__ == "__main__":
    unittest.main()
