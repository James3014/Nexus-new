import os
import unittest
import json
from unittest.mock import MagicMock, patch
from nexus.core.context_adapter import ContextAdapter

class TestContextAdapterUnit(unittest.TestCase):
    """
    🧬 Focused unit tests for ContextAdapter (P3)
    Covers provider selection, subprocess fallback, and passthrough behavior.
    """
    def setUp(self):
        self.mock_hub = MagicMock()
        # Mocking assemble_context and other hub methods
        self.mock_hub.assemble_context.return_value = "legacy context"
        self.mock_hub.legacy_attr = "legacy value"
        self.mock_hub.legacy_method.return_value = "legacy method return"

    def test_provider_selection_case_insensitive(self):
        """Test provider mode selection is case-insensitive."""
        with patch.dict(os.environ, {"NEXUS_CONTEXT_PROVIDER": "LEANCTX"}):
            adapter = ContextAdapter(self.mock_hub)
            self.assertEqual(adapter.provider_mode, "leanctx")
        
        with patch.dict(os.environ, {"NEXUS_CONTEXT_PROVIDER": "Legacy"}):
            adapter = ContextAdapter(self.mock_hub)
            self.assertEqual(adapter.provider_mode, "legacy")

    @patch("subprocess.run")
    def test_subprocess_timeout_fallback(self, mock_run):
        """Test fallback when lean-ctx subprocess times out."""
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired(cmd=["lean-ctx"], timeout=5)
        
        with patch.dict(os.environ, {"NEXUS_CONTEXT_PROVIDER": "leanctx"}):
            adapter = ContextAdapter(self.mock_hub)
            res = adapter.assemble_context("task-1", [1, 2])
            
            # Should fallback to legacy hub
            self.assertEqual(res, "legacy context")
            self.mock_hub.assemble_context.assert_called_once()

    @patch("subprocess.run")
    def test_subprocess_error_fallback(self, mock_run):
        """Test fallback when lean-ctx binary is missing or returns error."""
        # Scenario 1: Binary missing
        mock_run.side_effect = FileNotFoundError()
        with patch.dict(os.environ, {"NEXUS_CONTEXT_PROVIDER": "leanctx"}):
            adapter = ContextAdapter(self.mock_hub)
            res = adapter.assemble_context("task-2", [1])
            self.assertEqual(res, "legacy context")
            self.mock_hub.assemble_context.assert_called_once()
        
        # Scenario 2: Return code non-zero
        self.mock_hub.assemble_context.reset_mock()
        mock_run.side_effect = None
        mock_run.return_value = MagicMock(returncode=1, stderr="internal error")
        with patch.dict(os.environ, {"NEXUS_CONTEXT_PROVIDER": "leanctx"}):
            adapter = ContextAdapter(self.mock_hub)
            res = adapter.assemble_context("task-3", [1])
            self.assertEqual(res, "legacy context")
            self.mock_hub.assemble_context.assert_called_once()

    def test_passthrough_behavior_getattr(self):
        """Test ContextAdapter forwards unknown attributes to the legacy provider (ContextHub)."""
        adapter = ContextAdapter(self.mock_hub)
        
        # Test attribute passthrough
        self.assertEqual(adapter.legacy_attr, "legacy value")
        
        # Test method passthrough
        self.assertEqual(adapter.legacy_method(), "legacy method return")
        self.mock_hub.legacy_method.assert_called_once()

    @patch("subprocess.run")
    def test_assemble_repair_pack_merge_behavior(self, mock_run):
        """Test merging of lean-ctx and legacy packs for repair pack (Non-authoritative)."""
        self.mock_hub.assemble_repair_pack.return_value = {
            "authoritative_data": "must-keep",
            "overridable": "old"
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"overridable": "new", "extra": "info"})
        )
        
        with patch.dict(os.environ, {"NEXUS_CONTEXT_PROVIDER": "leanctx"}):
            adapter = ContextAdapter(self.mock_hub)
            diagnosis = MagicMock(summary="test sum", hotspots=["file.py"])
            res = adapter.assemble_repair_pack(diagnosis, [])
            
            # Merged results
            self.assertEqual(res["authoritative_data"], "must-keep")
            self.assertEqual(res["overridable"], "new")
            self.assertEqual(res["extra"], "info")

if __name__ == "__main__":
    unittest.main()
