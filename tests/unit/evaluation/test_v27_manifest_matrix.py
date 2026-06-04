import unittest
from nexus.services.local_heal.task_manifest import v27_expansion_manifest, LocalHealTaskSpec
from nexus.evaluation.manifest_manager import ManifestValidator

class TestV27ManifestHardened(unittest.TestCase):
    """
    [v27] Manifest Validation Matrix
    覆蓋缺欄位、錯型別、非法 lane、非法 policy、重複 ID 與跨域准入規則。
    """

    def test_reject_duplicate_ids(self):
        """[P0] 驗證：重複的 task_id 應被攔截"""
        spec = LocalHealTaskSpec(task_id="dup", kind="swebench", family="x", env_profile="y")
        known = {"dup"}
        with self.assertRaises(ValueError) as cm:
            ManifestValidator.validate_spec(spec, known)
        self.assertIn("Duplicate task_id", str(cm.exception))

    def test_reject_missing_domain_for_experimental(self):
        """[P0] 驗證：實驗性任務必須有明確的 domain_id"""
        spec = LocalHealTaskSpec(
            task_id="exp-1", kind="cross_domain_experimental", family="x", env_profile="y",
            domain_id="legacy" # Invalid for experimental
        )
        with self.assertRaises(ValueError) as cm:
            ManifestValidator.validate_spec(spec)
        self.assertIn("explicit domain_id required", str(cm.exception))

    def test_reject_unauthorized_baseline_entry(self):
        """[P0] 驗證：禁止實驗性任務未經攻堅直接進入 Baseline"""
        spec = LocalHealTaskSpec(
            task_id="exp-2", kind="cross_domain_experimental", family="x", env_profile="y",
            lane="baseline", domain_id="new-domain"
        )
        with self.assertRaises(ValueError) as cm:
            ManifestValidator.validate_spec(spec)
        self.assertIn("cannot enter 'baseline' lane directly", str(cm.exception))

    def test_reject_wrong_types(self):
        """[P0] 驗證：型別不符時應攔截 (Linus: Strong typing)"""
        spec = LocalHealTaskSpec(
            task_id=123, # type: ignore
            kind="swebench", family="x", env_profile="y"
        )
        with self.assertRaises(TypeError):
            ManifestValidator.validate_spec(spec)

if __name__ == "__main__":
    unittest.main()
