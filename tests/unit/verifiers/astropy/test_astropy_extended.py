import unittest
from nexus.verifiers.domain.astropy.fits_reader import FitsReader
from nexus.verifiers.domain.astropy.astrophysics_guard import AstropyAstrophysicsGuard

class TestAstropyExtended(unittest.TestCase):
    """
    [v27.3 T2] 延伸 Astropy 的測試邊界
    補足 Header Normalization, Round-trip Integrity, 以及座標變換的不變量驗證
    """
    
    def test_header_purity_violation(self):
        """驗證：修補程式不得無故刪除 FITS 強制要求的 Header (如 SIMPLE, BITPIX)"""
        patch = '''
        header = fits.Header()
        # Missing SIMPLE=T or other standard keys
        del header['SIMPLE']
        '''
        # 預期：應被攔截
        # 我們將擴充 AstropyAstrophysicsGuard 或是建立專屬的 IOGuard
        verdict = AstropyAstrophysicsGuard.evaluate("ast1", patch)
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.failure_tags[0].code, "MANDATORY_HEADER_MISSING")

    def test_coordinate_inconsistency(self):
        """驗證：混合不同座標系且未進行明確轉換的運算應被阻斷"""
        patch = '''
        from astropy.coordinates import SkyCoord, ICRS, Galactic
        c1 = SkyCoord(ra=10, dec=20, frame='icrs', unit='deg')
        c2 = SkyCoord(l=10, b=20, frame='galactic', unit='deg')
        # Dangerous operation: trying to compute distance/diff without alignment
        dist = c1.separation(c2) 
        '''
        # 雖然 astropy 會自動處理，但為了嚴謹，我們要求必須有 transform_to 或是對齊 frame
        verdict = AstropyAstrophysicsGuard.evaluate("ast2", patch)
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.failure_tags[0].code, "AMBIGUOUS_FRAME_ALIGNMENT")

if __name__ == "__main__":
    unittest.main()
