import unittest
from nexus.services.local_heal.assertion_extractor import AssertionExtractor

class TestAssertionExtractor(unittest.TestCase):
    
    def test_extract_simple_assertion_error(self):
        sample_output = """
        def test_normalize_key_boundaries():
        >       assert normalize_key('  User   Name  ') == 'user-name'
        E       AssertionError: assert 'user---name' == 'user-name'
        E         - user-name
        E         + user---name
        """
        results = AssertionExtractor.extract_counterexamples(sample_output)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["actual"], "user---name")
        self.assertEqual(results[0]["expected"], "user-name")

    def test_extract_multiple_assertions(self):
        sample_output = """
        E       AssertionError: assert 'api__token' == 'api-token'
        ...
        E       AssertionError: assert '' == 'empty'
        """
        results = AssertionExtractor.extract_counterexamples(sample_output)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["actual"], "api__token")
        self.assertEqual(results[0]["expected"], "api-token")
        self.assertEqual(results[1]["actual"], "")
        self.assertEqual(results[1]["expected"], "empty")

    def test_extract_with_pytest_prefix(self):
        sample_output = """
        E       assert 'a' == 'b'
        """
        results = AssertionExtractor.extract_counterexamples(sample_output)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["actual"], "a")
        self.assertEqual(results[0]["expected"], "b")

    def test_format_counterexamples(self):
        counterexamples = [
            {"actual": "user---name", "expected": "user-name"},
            {"actual": "api__token", "expected": "api-token"}
        ]
        formatted = AssertionExtractor.format_counterexamples(counterexamples)
        self.assertIn("- Expected: user-name | Actual: user---name", formatted)
        self.assertIn("- Expected: api-token | Actual: api__token", formatted)
