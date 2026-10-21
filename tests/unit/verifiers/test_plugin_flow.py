import re
import unittest

from nexus.committee.controller import CommitteeControllerV263
from nexus.verifiers.contracts import FailureTag, VerifierVerdict
from nexus.verifiers.registry import VerifierRegistry


def _name_sanity_verdict(candidate_id: str, patch: str) -> VerifierVerdict:
    # Same rule as the retired nexus.verifiers.domain.name_sanity.NameSanityVerifier.
    usages = set(re.findall(r"([a-zA-Z0-9_]+)\.", patch)) - {"self"}
    allowed = set(re.findall(r"import\s+([a-zA-Z0-9_]+)", patch))
    allowed |= set(re.findall(r"as\s+([a-zA-Z0-9_]+)", patch))
    allowed |= {"os", "sys", "time", "numpy", "np", "pandas", "pd"}
    missing = sorted(usages - allowed)
    if missing:
        return VerifierVerdict(
            verifier_name="name_sanity",
            candidate_id=candidate_id,
            passed=False,
            score=-5.0,
            failure_tags=[FailureTag(code="NAME_ERROR", description=f"MISSING: {missing}")],
        )
    return VerifierVerdict(
        verifier_name="name_sanity",
        candidate_id=candidate_id,
        passed=True,
        score=2.0 if usages else 1.0,
        failure_tags=[FailureTag(code="SUCCESS", description="All imports resolved")],
    )


class _StubNameSanityVerifier:
    """Test-local plugin; NameSanityVerifier was retired in Phase-2 batch C (#2584)."""

    def evaluate(self, candidate_id: str, patch: str) -> VerifierVerdict:
        return _name_sanity_verdict(candidate_id, patch)


class TestPluginArchitecture(unittest.TestCase):
    def setUp(self):
        VerifierRegistry.clear()

    def test_plugin_registration_and_execution(self):
        """驗證：外掛註冊後能自動被 Controller 執行"""
        # 1. 註冊外掛
        VerifierRegistry.register("name_sanity", _StubNameSanityVerifier())
        
        # 2. 執行控制器
        controller = CommitteeControllerV263("test-plugin")
        controller.enabled = True
        
        # 提供一個會觸發 NAME_ERROR 的候選 (使用未授權的 foo)
        proposals = [{"model": "7B", "attempt": 1, "raw_label": "r:0,p:3", "artifacts": ["foo.arange(10)"]}]
        
        receipt = controller.process_proposals(proposals)
        
        # 3. 驗證結果：應包含來自 name_sanity 的裁決
        v_names = [v.verifier_name for v in receipt.verdicts]
        self.assertIn("name_sanity", v_names)
        # 由於未 import foo，應為 False
        self.assertFalse(receipt.verdicts[0].passed)

if __name__ == "__main__":
    unittest.main()
