import unittest
from nexus.calibration.tuner import TemperatureScaler
from nexus.verifiers.packs.registry import PackRegistry
from nexus.verifiers.packs.astropy_pack import AstropyPack

class TestCalibrationAndPacks(unittest.TestCase):
    def test_temperature_scaling_effect(self):
        """[T5] 驗證：T > 1.0 時機率分布應更平滑 (降低過度自信)"""
        scaler = TemperatureScaler(temperature=1.5)
        # 高置信度被壓低
        self.assertLess(scaler.apply(0.9), 0.9)
        # 低置信度被拉高
        self.assertGreater(scaler.apply(0.1), 0.1)

    def test_pack_registry_activation(self):
        """[T7] 驗證：能根據 domain tags 正確啟動 Pack"""
        PackRegistry.clear()
        PackRegistry.register(AstropyPack())
        
        # 匹配標籤
        enabled = PackRegistry.get_enabled_packs(["astropy"])
        self.assertEqual(len(enabled), 1)
        self.assertEqual(enabled[0].name, "astropy_pack")
        
        # 不匹配標籤
        none_enabled = PackRegistry.get_enabled_packs(["web_frontend"])
        self.assertEqual(len(none_enabled), 0)

if __name__ == "__main__":
    unittest.main()
