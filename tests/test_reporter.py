import unittest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from nexus.services.reporter import Reporter

class TestReporter(unittest.TestCase):
    def setUp(self):
        self.project_root = Path("/tmp/nexus_test_reporter")
        self.project_root.mkdir(parents=True, exist_ok=True)
        self.tracelog_path = self.project_root / "tracelog.jsonl"
        self.reporter = Reporter(project_root=str(self.project_root), tracelog_path=self.tracelog_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.project_root)

    @patch("subprocess.run")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("sys.executable", "/usr/bin/python3")
    def test_voice_notify(self, _mock_exists, mock_run):
        self.reporter.voice_notify("Hello Test")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("notify.py", args[1])
        self.assertEqual(args[2], "Hello Test")

    @patch.dict("os.environ", {"NEXUS_AUDIO_NOTIFY": "0"}, clear=False)
    @patch("subprocess.run")
    def test_voice_notify_disabled_by_env(self, mock_run):
        self.reporter.voice_notify("Hello Test")
        mock_run.assert_not_called()

    def test_log_trace(self):
        self.reporter.log_trace("test_cmd", "test_task", "SUCCESS", tokens=100, score=0.8)
        
        self.assertTrue(self.tracelog_path.exists())
        with open(self.tracelog_path, "r") as f:
            line = f.readline()
            entry = json.loads(line)
            self.assertEqual(entry["command"], "test_cmd")
            self.assertEqual(entry["task"], "test_task")
            self.assertEqual(entry["status"], "SUCCESS")
            self.assertEqual(entry["tokens_used"], 100)
            self.assertEqual(entry["flashjudge_score"], 0.8)
            self.assertIn("timestamp", entry)

if __name__ == "__main__":
    unittest.main()
