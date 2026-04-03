import unittest
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from nexus.services.continuous_learning import _apply_semantic_patch

class TestP1AAnchors(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.doc_path = self.root / "TEST_DOC.md"
        self.doc_path.write_text("# Test Doc\n\n%% Footer %%", encoding="utf-8")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_anchor_creation_and_replacement(self):
        # 1. First write (should create anchor)
        _apply_semantic_patch(self.doc_path, "evolution", "task-001", "### Heading 1", "Body 1")
        content = self.doc_path.read_text()
        self.assertIn("<!-- nexus-anchor:evolution -->", content)
        self.assertIn("### Heading 1", content)
        self.assertIn("Body 1", content)

        # 2. Same ID update (should REPLACE)
        _apply_semantic_patch(self.doc_path, "evolution", "task-001", "### Heading 1 Updated", "Body 1 Updated")
        content = self.doc_path.read_text()
        self.assertIn("Body 1 Updated", content)
        self.assertNotIn("Body 1\n", content) # Old content should be gone
        self.assertEqual(content.count("task-001"), 2) # Start/End markers (1 pair)

        # 3. New ID (should PREPEND / Most Recent First)
        _apply_semantic_patch(self.doc_path, "evolution", "task-002", "### Heading 2", "Body 2")
        content = self.doc_path.read_text()
        idx1 = content.find("task-001")
        idx2 = content.find("task-002")
        self.assertTrue(idx2 < idx1, "Newer task should be prepended before older task")

if __name__ == "__main__":
    unittest.main()
