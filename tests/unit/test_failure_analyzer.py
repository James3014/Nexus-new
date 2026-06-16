import unittest
from nexus.services.local_heal.errors import PatchErrorKind
from nexus.services.local_heal.failure_analyzer import FailureAnalyzer

class TestFailureAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = FailureAnalyzer()

    def test_classify_search_mismatch(self):
        reason = "SEARCH_MISMATCH: The following block was not found in the file..."
        kind = self.analyzer.classify_patch_failure(reason)
        self.assertEqual(kind, PatchErrorKind.SEARCH_MISMATCH)

    def test_classify_syntax_error(self):
        reason = "SYNTAX_ERROR: IndentationError: expected an indented block"
        kind = self.analyzer.classify_patch_failure(reason)
        self.assertEqual(kind, PatchErrorKind.SYNTAX_ERROR)

    def test_classify_model_refusal(self):
        reason = "MODEL_REFUSAL: I cannot fulfill this request."
        kind = self.analyzer.classify_patch_failure(reason)
        self.assertEqual(kind, PatchErrorKind.REFUSAL_DETECTED)

    def test_classify_unknown_is_fallback(self):
        reason = "Something went wrong in the matrix."
        kind = self.analyzer.classify_patch_failure(reason)
        self.assertEqual(kind, PatchErrorKind.NO_BLOCKS_FOUND)

    def test_should_retry_infrastructure(self):
        self.assertFalse(self.analyzer.should_retry("MODEL_TIMEOUT"))
        self.assertFalse(self.analyzer.should_retry("MODEL_PROVIDER_ERROR"))

    def test_should_retry_logic(self):
        self.assertTrue(self.analyzer.should_retry("SEARCH_MISMATCH"))
        self.assertTrue(self.analyzer.should_retry("SYNTAX_ERROR"))

if __name__ == "__main__":
    unittest.main()
