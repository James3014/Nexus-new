import json
import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from nexus.services.continuous_learning import (
    validate_writeback_completion,
    refresh_writeback_status,
    _normalize_markdown
)

class TestWritebackValidation(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.todo_path = self.root / ".nexus" / "reports" / "writeback_todo.json"
        self.target_file = "docs/INDEX.md"
        self.target_path = self.root / self.target_file
        self.target_path.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _make_todo(self, task_id, block, anchor="evolution"):
        payload = {
            "task_id": task_id,
            "writeback_required": True,
            "items": [{
                "target": self.target_file,
                "anchor_id": anchor,
                "status": "completed",
                "expected_hash": hashlib.sha256(block.encode("utf-8")).hexdigest()
            }]
        }
        self.todo_path.parent.mkdir(parents=True, exist_ok=True)
        self.todo_path.write_text(json.dumps(payload), encoding="utf-8")

    def test_validate_pass(self):
        task_id = "T1"
        block = f"<!-- nexus-writeback:{task_id} -->\n### Auto Writeback: {task_id}\n\n- Delta\n<!-- /nexus-writeback:{task_id} -->"
        doc = f"# INDEX\n<!-- nexus-anchor:evolution -->\n{block}\n<!-- /nexus-anchor:evolution -->\n"
        self.target_path.write_text(doc, encoding="utf-8")
        self._make_todo(task_id, block)

        result = validate_writeback_completion(task_id, self.todo_path, self.root)
        self.assertTrue(result.ok)
        self.assertEqual(result.final_status, "fully_delivered")

    def test_validate_duplicate_anchor(self):
        task_id = "T1"
        block = "foo"
        doc = "<!-- nexus-anchor:evolution --><!-- /nexus-anchor:evolution -->\n<!-- nexus-anchor:evolution --><!-- /nexus-anchor:evolution -->"
        self.target_path.write_text(doc, encoding="utf-8")
        self._make_todo(task_id, block)

        result = validate_writeback_completion(task_id, self.todo_path, self.root)
        self.assertFalse(result.ok)
        self.assertEqual(result.fail_code, "WB_ANCHOR_DUPLICATE")

    def test_validate_hash_mismatch(self):
        task_id = "T1"
        block = f"<!-- nexus-writeback:{task_id} -->\nTruth\n<!-- /nexus-writeback:{task_id} -->"
        doc = f"<!-- nexus-anchor:evolution -->\n<!-- nexus-writeback:{task_id} -->\nLie\n<!-- /nexus-writeback:{task_id} -->\n<!-- /nexus-anchor:evolution -->"
        self.target_path.write_text(doc, encoding="utf-8")
        self._make_todo(task_id, block)

        result = validate_writeback_completion(task_id, self.todo_path, self.root)
        self.assertFalse(result.ok)
        self.assertEqual(result.fail_code, "WB_CONTENT_MISMATCH")

    def test_validate_sort_violation(self):
        t1 = "<!-- nexus-writeback:T1 -->T1<!-- /nexus-writeback:T1 -->"
        t2 = "<!-- nexus-writeback:T2 -->T2<!-- /nexus-writeback:T2 -->"
        # T2 is new, but T1 is first in doc
        doc = f"<!-- nexus-anchor:evolution -->\n{t1}\n{t2}\n<!-- /nexus-anchor:evolution -->"
        self.target_path.write_text(doc, encoding="utf-8")
        self._make_todo("T2", t2)

        result = validate_writeback_completion("T2", self.todo_path, self.root)
        self.assertFalse(result.ok)
        self.assertEqual(result.fail_code, "WB_SORT_VIOLATION")

    def test_refresh_status_logic(self):
        task_id = "T1"
        block = "<!-- nexus-writeback:T1 -->T1<!-- /nexus-writeback:T1 -->"
        doc = f"<!-- nexus-anchor:evolution -->\n{block}\n<!-- /nexus-anchor:evolution -->"
        self.target_path.write_text(doc, encoding="utf-8")
        self._make_todo(task_id, block)

        res = refresh_writeback_status(self.root, source="test")
        self.assertEqual(res["delivery_status"], "fully_delivered")
        
        # Check event log
        val_log = self.root / ".nexus" / "events" / "writeback_validation.jsonl"
        self.assertTrue(val_log.exists())
        last_event = json.loads(val_log.read_text().splitlines()[-1])
        self.assertEqual(last_event["status"], "pass")

if __name__ == "__main__":
    unittest.main()
