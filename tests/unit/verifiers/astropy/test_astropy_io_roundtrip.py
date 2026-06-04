import unittest
from nexus.verifiers.domain.astropy.fits_reader import FitsReader
class TestAstropy(unittest.TestCase):
    def test_read(self):
        self.assertTrue(FitsReader.read_header("...")["SIMPLE"])
