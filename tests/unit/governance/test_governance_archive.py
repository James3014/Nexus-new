import unittest
from nexus.governance.application.archive_manager import ArchiveManager
from nexus.governance.application.finalization_report import FinalizationReportBuilder
from nexus.ci.verification_bundle import VerificationBundleFactory
from nexus.evaluation.governance.metrics_collector import GovernanceMonitor

class TestGovernanceArchive(unittest.TestCase):
    """
    🗄️ [v27.1 Archive] TDD Matrix
    驗證治理資產歸檔的一致性與不可篡改。
    """

    def test_archive_integrity(self):
        """[P0] 驗證：歸檔是否包含所有核心資產"""
        bundle = VerificationBundleFactory.create_bundle("h1", "p1", ["r1"])
        monitor = GovernanceMonitor()
        report = FinalizationReportBuilder.build_seal_report(bundle, monitor.generate_report())
        adr_hashes = {"ADR-0010": "abc", "ADR-0011": "def"}
        
        archive = ArchiveManager.create_archive("v27.1", report, bundle, adr_hashes)
        
        self.assertEqual(archive.version, "v27.1")
        self.assertIsNotNone(archive.archive_hash)
        self.assertEqual(archive.approved_adr_hashes["ADR-0010"], "abc")

    def test_archive_hash_drift(self):
        """[P0] 驗證：任何元數據變更都會改變歸檔雜湊"""
        bundle = VerificationBundleFactory.create_bundle("h1", "p1", ["r1"])
        monitor = GovernanceMonitor()
        report = FinalizationReportBuilder.build_seal_report(bundle, monitor.generate_report())
        
        a1 = ArchiveManager.create_archive("v27.1", report, bundle, {"ADR-0010": "abc"})
        a2 = ArchiveManager.create_archive("v27.1", report, bundle, {"ADR-0010": "dirty"})
        
        self.assertNotEqual(a1.archive_hash, a2.archive_hash)

if __name__ == "__main__":
    unittest.main()
