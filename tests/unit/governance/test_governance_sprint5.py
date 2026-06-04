import unittest
from nexus.governance.application.finalization_report import FinalizationReportBuilder
from nexus.ci.verification_bundle import VerificationBundleFactory
from nexus.evaluation.governance.metrics_collector import GovernanceMonitor

class TestSprint5Sealing(unittest.TestCase):
    """
    📜 [v27.1 Sprint 5] TDD Matrix: Operation Sealing
    驗證結案報告的聚合完整性與規格凍結。
    """

    def test_final_report_includes_all_receipts(self):
        """[P0] 驗證：報告是否聚合了 Bundle 與 Metrics"""
        bundle = VerificationBundleFactory.create_bundle("hash123", "p1", ["r1"])
        monitor = GovernanceMonitor()
        metrics = monitor.generate_report()
        
        report = FinalizationReportBuilder.build_seal_report(bundle, metrics)
        
        self.assertEqual(report.version, "v27.1")
        self.assertEqual(report.bundle.bundle_id.startswith("B-"), True)
        self.assertEqual(report.metrics.manifest_pass_rate, 1.0)

    def test_blocker_taxonomy_mapping(self):
        """[Domain] 驗證：Blocker 錯誤碼映射是否正確"""
        from nexus.governance.domain.blocker_taxonomy import BlockerCode, BlockerRegistry
        desc = BlockerRegistry.get_description(BlockerCode.DRIFT_DETECTED)
        self.assertIn("hash drifted", desc)

if __name__ == "__main__":
    unittest.main()
