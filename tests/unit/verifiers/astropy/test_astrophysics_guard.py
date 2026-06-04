import unittest
from nexus.verifiers.domain.astropy.astrophysics_guard import AstropyAstrophysicsGuard

class TestAstrophysicsGuard(unittest.TestCase):
    
    def test_unit_stripping_is_blocked(self):
        """驗證：缺乏 astropy 單位保護的加減法會被擋下"""
        patch = '''
        def update_velocity(v, delta):
            v += delta # Dangerous! Strips units if not careful.
            return v
        '''
        verdict = AstropyAstrophysicsGuard.evaluate("t1", patch)
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.failure_tags[0].code, "UNIT_STRIPPING_RISK")

    def test_safe_unit_math_is_allowed(self):
        """驗證：使用 astropy.units (u.) 的數學運算允許通過"""
        patch = '''
        import astropy.units as u
        def update_velocity(v, delta):
            v += delta * u.m / u.s
            return v
        '''
        verdict = AstropyAstrophysicsGuard.evaluate("t2", patch)
        self.assertTrue(verdict.passed)

    def test_rigid_frame_is_blocked(self):
        """驗證：硬編碼 ICRS 但未提供 transform_to 會被擋下"""
        patch = '''
        class CustomStar:
            frame = ICRS()
        '''
        verdict = AstropyAstrophysicsGuard.evaluate("t3", patch)
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.failure_tags[0].code, "RIGID_COORDINATE_FRAME")

if __name__ == "__main__":
    unittest.main()
