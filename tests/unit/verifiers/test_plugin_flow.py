import unittest
from nexus.verifiers.registry import VerifierRegistry
from nexus.verifiers.domain.name_sanity import NameSanityVerifier
from nexus.verifiers.domain.inheritance import DeepInheritanceVerifier
from nexus.committee.controller import CommitteeControllerV263

class TestPluginArchitecture(unittest.TestCase):
    def setUp(self):
        VerifierRegistry.clear()

    def test_plugin_registration_and_execution(self):
        """驗證：外掛註冊後能自動被 Controller 執行"""
        # 1. 註冊外掛
        VerifierRegistry.register("name_sanity", NameSanityVerifier())
        
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
