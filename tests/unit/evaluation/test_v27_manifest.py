import unittest
from nexus.services.local_heal.task_manifest import v27_expansion_manifest, LocalHealTaskSpec
from nexus.evaluation.manifest_manager import ManifestValidator

class TestV27Manifest(unittest.TestCase):
    """
    [v27] Manifest Expansion & Validation Testing
    職責: 鎖死「欄位合法性、Lane 規則、Promotion Policy」三位一體治理。
    """
    def test_v27_fields_presence(self):
        specs = v27_expansion_manifest()
        self.assertGreater(len(specs), 0)
        
        s = specs[0]
        self.assertEqual(s.domain_id, "scikit_learn")
        self.assertEqual(s.lane, "migration")
        self.assertIn("target_recovery", s.extension_metadata)

    def test_manifest_validation_rejects_incomplete(self):
        """[T1] 驗證：缺 domain_id 應攔截"""
        bad_spec_1 = LocalHealTaskSpec(
            task_id="bad-1", kind="cross_domain_experimental", family="x", env_profile="y",
            domain_id="" # Empty
        )
        with self.assertRaises(ValueError) as cm:
            ManifestValidator.validate_spec(bad_spec_1)
        self.assertIn("explicit domain_id required", str(cm.exception))

    def test_manifest_validation_rejects_illegal_lane(self):
        """[T2] 驗證：非法車道名稱應攔截"""
        bad_spec_2 = LocalHealTaskSpec(
            task_id="bad-2", kind="swebench", family="x", env_profile="y",
            lane="random_experimental_lane" # type: ignore
        )
        with self.assertRaises(ValueError) as cm:
            ManifestValidator.validate_spec(bad_spec_2)
        self.assertIn("Illegal Lane", str(cm.exception))

    def test_manifest_validation_rejects_illegal_policy(self):
        """[T3] 驗證：非法晉升政策應攔截"""
        bad_spec_3 = LocalHealTaskSpec(
            task_id="bad-3", kind="swebench", family="x", env_profile="y",
            promotion_policy="cowboy_merge" 
        )
        with self.assertRaises(ValueError) as cm:
            ManifestValidator.validate_spec(bad_spec_3)
        self.assertIn("Illegal Promotion Policy", str(cm.exception))

    def test_migration_lane_requires_metadata(self):
        """[T4] 驗證：Migration 車道必須具備 extension_metadata"""
        bad_spec_4 = LocalHealTaskSpec(
            task_id="bad-4", kind="cross_domain_experimental", family="x", env_profile="y",
            domain_id="flask", # Fix first error to reach lane check
            lane="migration",
            extension_metadata={} # Empty
        )
        with self.assertRaises(ValueError) as cm:
            ManifestValidator.validate_spec(bad_spec_4)
        self.assertIn("extension_metadata required for lane 'migration'", str(cm.exception))

if __name__ == "__main__":
    unittest.main()
